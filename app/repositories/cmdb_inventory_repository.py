"""Persistence operations for spreadsheet-owned inventory and review audit."""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import Integer, String, cast, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cmdb_inventory import CMDBInventoryAudit, CMDBInventoryImport, CMDBInventoryRecord
from app.services.cmdb_inventory_service import ParsedInventory


class CMDBInventoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def summary(self) -> Dict[str, Any]:
        result = await self.session.execute(
            select(CMDBInventoryRecord.inventory_type, func.count(),
                   func.sum(CMDBInventoryRecord.is_validated.cast(Integer)))
            .group_by(CMDBInventoryRecord.inventory_type)
        )
        counts = {kind: {"total": total, "validated": validated or 0}
                  for kind, total, validated in result.all()}
        imported_result = await self.session.execute(
            select(CMDBInventoryImport.inventory_type).distinct()
        )
        imported_types = set(imported_result.scalars().all())
        for kind in ("server", "network", "telecom"):
            counts.setdefault(kind, {"total": 0, "validated": 0})
        return {
            "total_records": sum(value["total"] for value in counts.values()),
            "server_count": counts["server"]["total"],
            "network_count": counts["network"]["total"],
            "telecom_count": counts["telecom"]["total"],
            "validated_count": sum(value["validated"] for value in counts.values()),
            "pending_count": sum(value["total"] - value["validated"] for value in counts.values()),
            "imported": {kind: kind in imported_types for kind in ("server", "network", "telecom")},
            "source": "database",
            "fallback_used": False,
        }

    async def list_inventory(
        self,
        inventory_type: Optional[str],
        page: int = 1,
        page_size: int = 50,
        search: Optional[str] = None,
    ) -> Dict[str, Any]:
        statement = select(CMDBInventoryRecord)
        count_statement = select(func.count()).select_from(CMDBInventoryRecord)
        if inventory_type:
            statement = statement.where(CMDBInventoryRecord.inventory_type == inventory_type)
            count_statement = count_statement.where(CMDBInventoryRecord.inventory_type == inventory_type)
        if search and search.strip():
            pattern = f"%{search.strip()}%"
            search_filter = or_(
                CMDBInventoryRecord.name.ilike(pattern),
                CMDBInventoryRecord.source_sheet.ilike(pattern),
                cast(CMDBInventoryRecord.data, String).ilike(pattern),
            )
            statement = statement.where(search_filter)
            count_statement = count_statement.where(search_filter)
        total = (await self.session.execute(count_statement)).scalar_one()
        result = await self.session.execute(
            statement.order_by(CMDBInventoryRecord.source_order)
            .offset((page - 1) * page_size).limit(page_size)
        )
        items = [record.to_dict() for record in result.scalars().all()]
        headers = await self._latest_headers(inventory_type)
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
            "headers": headers,
        }

    async def _latest_headers(self, inventory_type: Optional[str]) -> Dict[str, list]:
        statement = select(CMDBInventoryImport).order_by(CMDBInventoryImport.imported_at.desc())
        if inventory_type:
            statement = statement.where(CMDBInventoryImport.inventory_type == inventory_type)
        result = await self.session.execute(statement)
        imports = result.scalars().all()
        latest = {}
        for batch in imports:
            latest.setdefault(batch.inventory_type, batch.headers)
        return latest

    async def replace_inventory(
        self, parsed: ParsedInventory, source_file: str, actor: str, inventory_type: str
    ) -> None:
        await self.session.execute(
            delete(CMDBInventoryRecord).where(CMDBInventoryRecord.inventory_type == inventory_type)
        )
        for record in parsed.records:
            self.session.add(CMDBInventoryRecord(
                inventory_type=inventory_type,
                source_key=f"{record['source_sheet']}:{record['source_row']}",
                name=record["name"],
                source_file=source_file,
                source_sheet=record["source_sheet"],
                source_row=record["source_row"],
                source_order=record["source_order"],
                data=record["data"],
            ))
        self.session.add(CMDBInventoryImport(
            inventory_type=inventory_type,
            source_file=source_file,
            headers=parsed.headers,
            imported_count=len(parsed.records),
            imported_by=actor,
        ))
        self.session.add(CMDBInventoryAudit(
            inventory_type=inventory_type,
            action="replace_import",
            actor=actor,
            details={"source_file": source_file, "record_count": len(parsed.records)},
        ))
        await self.session.flush()

    async def create_record(
        self, inventory_type: str, source_sheet: str, name: str, data: list, actor: str
    ) -> Dict[str, Any]:
        if inventory_type not in {"server", "network", "telecom"}:
            raise ValueError("Inventory type must be server, network, or telecom.")
        clean_name = name.strip()
        clean_sheet = source_sheet.strip()
        if not clean_name or len(clean_name) > 512 or not clean_sheet or len(clean_sheet) > 255:
            raise ValueError("Name and source sheet are required.")
        if not isinstance(data, list) or not data:
            raise ValueError("At least one inventory field is required.")
        for index, cell in enumerate(data):
            if (not isinstance(cell, dict) or set(cell) != {"index", "header", "value"}
                    or cell["index"] != index or not isinstance(cell["header"], str)
                    or not cell["header"].strip()):
                raise ValueError("Inventory fields must preserve a valid ordered header list.")
            value = cell["value"]
            if value is not None and not isinstance(value, (str, int, float, bool)):
                raise ValueError("Inventory fields must be plain text, numbers, or empty.")
        max_order = (await self.session.execute(
            select(func.max(CMDBInventoryRecord.source_order)).where(
                CMDBInventoryRecord.inventory_type == inventory_type
            )
        )).scalar_one_or_none()
        max_row = (await self.session.execute(
            select(func.max(CMDBInventoryRecord.source_row)).where(
                CMDBInventoryRecord.inventory_type == inventory_type,
                CMDBInventoryRecord.source_sheet == clean_sheet,
            )
        )).scalar_one_or_none()
        identifier = uuid.uuid4()
        record = CMDBInventoryRecord(
            id=identifier,
            inventory_type=inventory_type,
            source_key=f"manual:{identifier}",
            name=clean_name,
            source_file="Manual entry",
            source_sheet=clean_sheet,
            source_row=int(max_row or 0) + 1,
            source_order=int(-1 if max_order is None else max_order) + 1,
            data=data,
        )
        self.session.add(record)
        self.session.add(CMDBInventoryAudit(
            inventory_type=inventory_type,
            record_id=str(identifier),
            action="create",
            actor=actor,
            details={"name": clean_name, "source_sheet": clean_sheet, "data": data},
        ))
        await self.session.flush()
        return record.to_dict()

    async def get_record(self, record_id: str) -> Optional[Dict[str, Any]]:
        record = await self._record(record_id)
        return record.to_dict() if record else None

    async def validate_record(self, record_id: str, actor: str) -> Optional[Dict[str, Any]]:
        record = await self._record(record_id)
        if not record:
            return None
        record.is_validated = True
        record.validated_at = datetime.now(timezone.utc)
        record.validated_by = actor
        record.updated_at = record.validated_at
        self.session.add(CMDBInventoryAudit(
            inventory_type=record.inventory_type,
            record_id=str(record.id),
            action="validate",
            actor=actor,
            details={"name": record.name},
        ))
        await self.session.flush()
        return record.to_dict()

    async def validate_field(self, record_id: str, field_index: int, actor: str) -> Optional[Dict[str, Any]]:
        record = await self._record(record_id)
        if not record:
            return None
        if not 0 <= field_index < len(record.data):
            raise ValueError("Field index is outside the imported workbook columns.")
        now = datetime.now(timezone.utc)
        field = record.data[field_index]
        reviews = dict(record.field_reviews or {})
        reviews[str(field_index)] = {
            "header": field["header"],
            "value": field["value"],
            "validated_at": now.isoformat(),
            "validated_by": actor,
        }
        record.field_reviews = reviews
        record.is_validated = len(reviews) == len(record.data)
        record.validated_at = now if record.is_validated else None
        record.validated_by = actor if record.is_validated else None
        record.updated_at = now
        self.session.add(CMDBInventoryAudit(
            inventory_type=record.inventory_type,
            record_id=str(record.id),
            action="validate_field",
            actor=actor,
            details={"field_index": field_index, "header": field["header"], "value": field["value"]},
        ))
        await self.session.flush()
        return record.to_dict()

    async def update_record(
        self, record_id: str, name: str, data: Dict[str, Any], actor: str
    ) -> Optional[Dict[str, Any]]:
        record = await self._record(record_id)
        if not record:
            return None
        clean_name = name.strip()
        if not clean_name or len(clean_name) > 512:
            raise ValueError("Name must contain 1 to 512 characters.")
        if not isinstance(data, list) or len(data) != len(record.data):
            raise ValueError("Edited fields must match the imported workbook columns.")
        reviews = dict(record.field_reviews or {})
        for index, (cell, original) in enumerate(zip(data, record.data)):
            if (not isinstance(cell, dict) or set(cell) != {"index", "header", "value"}
                    or cell["index"] != index or cell["header"] != original["header"]):
                raise ValueError("Workbook column order and labels cannot be changed during row editing.")
            value = cell["value"]
            if value is not None and not isinstance(value, (str, int, float, bool)):
                raise ValueError("Inventory fields must be plain text, numbers, or empty.")
            if isinstance(value, str) and len(value) > 10000:
                raise ValueError("Inventory field values cannot exceed 10,000 characters.")
        if len(json.dumps(data, ensure_ascii=True, allow_nan=False)) > 200000:
            raise ValueError("Edited inventory record is too large.")

        before = {"name": record.name, "data": record.data}
        for index, (cell, original) in enumerate(zip(data, record.data)):
            if cell["value"] != original["value"]:
                reviews.pop(str(index), None)
        record.name = clean_name
        record.data = data
        record.field_reviews = reviews
        now = datetime.now(timezone.utc)
        record.is_validated = len(reviews) == len(data)
        latest_review = max(reviews.values(), key=lambda review: review["validated_at"]) if reviews else None
        record.validated_at = datetime.fromisoformat(latest_review["validated_at"]) if record.is_validated and latest_review else None
        record.validated_by = latest_review["validated_by"] if record.is_validated and latest_review else None
        record.updated_at = now
        self.session.add(CMDBInventoryAudit(
            inventory_type=record.inventory_type,
            record_id=str(record.id),
            action="edit",
            actor=actor,
            details={"before": before, "after": {"name": clean_name, "data": data}},
        ))
        await self.session.flush()
        return record.to_dict()

    async def delete_record(self, record_id: str, actor: str) -> Optional[Dict[str, Any]]:
        record = await self._record(record_id)
        if not record:
            return None
        result = record.to_dict()
        self.session.add(CMDBInventoryAudit(
            inventory_type=record.inventory_type,
            record_id=str(record.id),
            action="delete",
            actor=actor,
            details={"name": record.name, "data": record.data},
        ))
        await self.session.delete(record)
        await self.session.flush()
        return result

    async def _record(self, record_id: str) -> Optional[CMDBInventoryRecord]:
        try:
            identifier = uuid.UUID(record_id)
        except (ValueError, TypeError, AttributeError):
            return None
        result = await self.session.execute(
            select(CMDBInventoryRecord).where(CMDBInventoryRecord.id == identifier)
        )
        return result.scalar_one_or_none()