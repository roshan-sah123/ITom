"""Parsing and validation helpers for spreadsheet-owned CMDB inventories."""

from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from typing import Any, Dict, List

from openpyxl import load_workbook


NAME_HEADERS = {
    "computer name",
    "host name",
    "hostname",
    "name",
    "server name",
    "serial no",
    "serial number",
}


@dataclass
class ParsedInventory:
    sheet_name: str
    headers: Dict[str, List[str]]
    records: List[Dict[str, Any]]


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _headers(row: tuple) -> List[str]:
    result = ["" if value is None else str(value) for value in row]
    while result and not result[-1].strip():
        result.pop()
    return result


def _find_header(sheet):
    for row_number, values in enumerate(
        sheet.iter_rows(min_row=1, max_row=30, values_only=True),
        1,
    ):
        nonempty = [value for value in values if value is not None and str(value).strip()]
        if len(nonempty) >= 2 and sum(isinstance(value, str) for value in nonempty) >= 2:
            return row_number, _headers(values)
        if len(nonempty) == 1 and isinstance(nonempty[0], str) and nonempty[0].strip().casefold() in NAME_HEADERS:
            return row_number, _headers(values)
    raise ValueError(f"No recognizable column header row in sheet '{sheet.title}'.")


def _record_name(data: Dict[str, Any], source_row: int) -> str:
    for cell in data:
        if cell["header"].strip().casefold() in NAME_HEADERS and cell["value"] is not None:
            text = str(cell["value"]).strip()
            if text:
                return text
    return f"Inventory row {source_row}"


def _selected_sheets(workbook, inventory_type: str):
    if inventory_type == "server":
        sheets = []
        for sheet in workbook.worksheets:
            try:
                _find_header(sheet)
            except ValueError:
                continue
            sheets.append(sheet)
        if not sheets:
            raise ValueError("Server workbook contains no populated inventory sheets.")
        return sheets
    if inventory_type == "network":
        sheets = [sheet for sheet in workbook.worksheets if sheet.title.strip().casefold() == "network inventory"]
        return sheets or [workbook.worksheets[0]]
    if inventory_type == "telecom":
        for sheet in workbook.worksheets:
            try:
                _find_header(sheet)
            except ValueError:
                continue
            return [sheet]
        raise ValueError("Telecom workbook contains no populated inventory sheet.")
    raise ValueError("Inventory type must be server, network, or telecom.")


def parse_inventory_workbook(content: bytes, inventory_type: str, filename: str) -> ParsedInventory:
    """Parse the supported sheets while retaining each workbook field and row."""
    del filename
    try:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        raise ValueError("Upload a valid .xlsx workbook.") from exc

    try:
        selected = _selected_sheets(workbook, inventory_type)
        output_headers = {}
        records = []
        first_sheet = selected[0].title
        source_order = 0

        for sheet in selected:
            header_row, headers = _find_header(sheet)
            output_headers[sheet.title] = headers

            for source_row, values in enumerate(
                sheet.iter_rows(min_row=header_row + 1, values_only=True),
                header_row + 1,
            ):
                if not any(value is not None and str(value).strip() for value in values):
                    continue
                data = [
                    {"index": index, "header": header,
                     "value": _json_value(values[index]) if index < len(values) else None}
                    for index, header in enumerate(headers)
                ]
                records.append({
                    "name": _record_name(data, source_row),
                    "source_sheet": sheet.title,
                    "source_row": source_row,
                    "source_order": source_order,
                    "data": data,
                })
                source_order += 1

        if not records:
            raise ValueError("The selected workbook sheets contain no inventory rows.")
        return ParsedInventory(first_sheet, output_headers, records)
    finally:
        workbook.close()