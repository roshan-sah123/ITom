"""Read-only inventory access for operator-provided asset workbooks."""

import logging
import math
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from zipfile import BadZipFile

import openpyxl
from openpyxl.utils.exceptions import InvalidFileException

logger = logging.getLogger(__name__)


class AssetInventoryCategory(str, Enum):
    SERVER = "server"
    NETWORK = "network"
    TELECOM = "telecom"


_CATEGORY_DETAILS = {
    AssetInventoryCategory.SERVER: ("Servers", "server.xlsx"),
    AssetInventoryCategory.NETWORK: ("Network devices", "network.xlsx"),
    AssetInventoryCategory.TELECOM: ("Telecom", "telecom.xlsx"),
}
_HEADER_SCAN_LIMIT = 50
_ALLOWED_PAGE_SIZES = {10, 25, 50, 100}


class AssetInventoryUnavailable(Exception):
    """A configured workbook is missing or cannot be read safely."""


class AssetInventoryService:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory)

    def summary(self) -> dict:
        items = []
        for category, (label, _) in _CATEGORY_DETAILS.items():
            try:
                columns, records = self._load(category)
            except AssetInventoryUnavailable as error:
                items.append({
                    "category": category.value,
                    "label": label,
                    "data_available": False,
                    "total": None,
                    "error": str(error),
                })
            else:
                items.append({
                    "category": category.value,
                    "label": label,
                    "data_available": True,
                    "total": len(records),
                    "column_count": len(columns),
                })
        return {
            "data_available": any(item["data_available"] for item in items),
            "items": items,
        }

    def list_inventory(
        self,
        category: AssetInventoryCategory | str,
        page: int = 1,
        page_size: int = 25,
        search: str | None = None,
    ) -> dict:
        if page < 1:
            raise ValueError("page must be at least 1")
        if page_size not in _ALLOWED_PAGE_SIZES:
            raise ValueError(
                f"page_size must be one of {sorted(_ALLOWED_PAGE_SIZES)}"
            )
        selected = AssetInventoryCategory(category)
        columns, records = self._load(selected)
        term = (search or "").strip().casefold()
        filtered = [
            record
            for record in records
            if not term
            or any(term in str(value).casefold() for value in record.values() if value is not None)
        ]
        total = len(filtered)
        start = (page - 1) * page_size
        return {
            "category": selected.value,
            "columns": columns,
            "items": filtered[start : start + page_size],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, math.ceil(total / page_size)),
        }

    def _load(self, category: AssetInventoryCategory) -> tuple[list[str], list[dict]]:
        snapshot = self.snapshot(category)
        return snapshot["columns"], [row["values"] for row in snapshot["rows"]]

    def snapshot(self, category: AssetInventoryCategory) -> dict:
        label, filename = _CATEGORY_DETAILS[category]
        path = self.directory / filename
        try:
            path.stat()
        except FileNotFoundError as error:
            raise AssetInventoryUnavailable(
                f"{label} inventory workbook is not available."
            ) from error
        except OSError as error:
            logger.warning(
                "Could not access asset inventory workbook category=%s error_type=%s",
                category.value,
                type(error).__name__,
            )
            raise AssetInventoryUnavailable(
                f"{label} inventory workbook could not be accessed."
            ) from error

        try:
            workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
        except (BadZipFile, InvalidFileException, OSError, ValueError) as error:
            logger.warning(
                "Could not read asset inventory workbook category=%s error_type=%s",
                category.value,
                type(error).__name__,
            )
            raise AssetInventoryUnavailable(
                f"{label} inventory workbook could not be read."
            ) from error

        try:
            selected = self._select_header(workbook)
            if selected is None:
                raise AssetInventoryUnavailable(
                    f"{label} inventory workbook has no usable header row."
                )
            sheet, header_row, headers = selected
            columns = self._unique_headers(headers)
            records = []
            for row_number, row in enumerate(sheet.iter_rows(
                min_row=header_row + 1,
                max_col=len(columns),
                values_only=True,
            ), start=header_row + 1):
                if not any(value not in (None, "") for value in row):
                    continue
                records.append({
                    "source_row": row_number,
                    "values": {
                        column: self._json_value(row[index] if index < len(row) else None)
                        for index, column in enumerate(columns)
                    },
                })
            return {"columns": columns, "rows": records, "source_sheet": sheet.title, "source_file": filename}
        finally:
            workbook.close()

    @staticmethod
    def _select_header(workbook):
        candidates = []
        for sheet_index, sheet in enumerate(workbook.worksheets):
            scan_end = min(sheet.max_row, _HEADER_SCAN_LIMIT)
            for row_index, row in enumerate(
                sheet.iter_rows(
                    min_row=1,
                    max_row=scan_end,
                    values_only=True,
                ),
                start=1,
            ):
                populated = [
                    (index, value)
                    for index, value in enumerate(row)
                    if value not in (None, "")
                ]
                distinct = {
                    str(value).strip().casefold()
                    for _, value in populated
                    if str(value).strip()
                }
                if len(populated) < 2 or len(distinct) < 2:
                    continue
                last_column = populated[-1][0] + 1
                headers = list(row[:last_column])
                candidates.append(
                    (len(populated), len(distinct), -sheet_index, -row_index, sheet, row_index, headers)
                )
        if not candidates:
            return None
        _, _, _, _, sheet, row_index, headers = max(candidates, key=lambda item: item[:4])
        return sheet, row_index, headers

    @staticmethod
    def _unique_headers(headers: list) -> list[str]:
        result = []
        seen = {}
        for index, value in enumerate(headers, start=1):
            base = str(value).strip() if value is not None else ""
            if not base:
                base = f"Column {index}"
            key = base.casefold()
            seen[key] = seen.get(key, 0) + 1
            result.append(base if seen[key] == 1 else f"{base} ({seen[key]})")
        return result

    @staticmethod
    def _json_value(value):
        if value is None or isinstance(value, (str, int, bool)):
            return value
        if isinstance(value, float):
            return value if math.isfinite(value) else None
        if isinstance(value, (datetime, date, time)):
            return value.isoformat()
        return str(value)
