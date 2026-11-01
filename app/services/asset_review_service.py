import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import Integer, String, cast, func, or_, select, update

from app.models.asset_review import AssetInventoryAudit, AssetInventoryBatch, AssetInventoryRecord
from app.services.asset_inventory_service import AssetInventoryCategory, AssetInventoryUnavailable


class AssetReviewConflict(Exception):
    pass


class AssetReviewService:
    def __init__(self, session, source):
        self.session, self.source = session, source

    async def ensure_source(self, category):
        batch = await self.session.get(AssetInventoryBatch, category.value)
        if batch:
            return batch
        snapshot = await asyncio.to_thread(self.source.snapshot, category)
        batch = AssetInventoryBatch(category=category.value, source_file=snapshot["source_file"],
                                    source_sheet=snapshot["source_sheet"], columns=snapshot["columns"])
        self.session.add(batch)
        for order, row in enumerate(snapshot["rows"]):
            data = [{"index": index, "header": header, "value": row["values"][header]}
                    for index, header in enumerate(snapshot["columns"])]
            name = next((str(cell["value"]).strip() for cell in data
                         if cell["header"].casefold() in {"host name", "hostname", "computer name", "server name", "name", "serial number", "serial no"}
                         and cell["value"] not in (None, "")), f"Inventory row {row['source_row']}")
            self.session.add(AssetInventoryRecord(
                category=category.value, source_key=f"{snapshot['source_sheet']}:{row['source_row']}",
                name=name, source_file=batch.source_file, source_sheet=batch.source_sheet,
                source_row=row["source_row"], source_order=order, data=data))
        await self.session.flush()
        return batch

    async def summary(self):
        items = []
        for category, label in zip(AssetInventoryCategory, ["Servers", "Network devices", "Telecom"]):
            try:
                batch = await self.ensure_source(category)
            except AssetInventoryUnavailable as error:
                items.append({"category": category.value, "label": label, "data_available": False, "total": None, "error": str(error)})
                continue
            counts = (await self.session.execute(select(func.count(), func.sum(cast(AssetInventoryRecord.is_validated, Integer)))
                .where(AssetInventoryRecord.category == category.value, AssetInventoryRecord.is_deleted.is_(False)))).one()
            items.append({"category": category.value, "label": label, "data_available": True, "total": counts[0],
                          "validated": counts[1] or 0, "pending": counts[0] - (counts[1] or 0),
                          "column_count": len(batch.columns)})
        return {"data_available": any(item["data_available"] for item in items), "items": items}

    async def list(self, category, page, page_size, search):
        batch = await self.ensure_source(category)
        conditions = [AssetInventoryRecord.category == category.value, AssetInventoryRecord.is_deleted.is_(False)]
        if search.strip():
            literal = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{literal}%"
            conditions.append(or_(AssetInventoryRecord.name.ilike(pattern, escape="\\"),
                AssetInventoryRecord.source_sheet.ilike(pattern, escape="\\"),
                cast(AssetInventoryRecord.data, String).ilike(pattern, escape="\\")))
        total = (await self.session.execute(select(func.count()).select_from(AssetInventoryRecord).where(*conditions))).scalar_one()
        rows = (await self.session.execute(select(AssetInventoryRecord).where(*conditions)
            .order_by(AssetInventoryRecord.source_order, AssetInventoryRecord.id)
            .offset((page - 1) * page_size).limit(page_size))).scalars().all()
        return {"category": category.value, "columns": batch.columns, "source_sheet": batch.source_sheet,
                "items": [self.serialize(row) for row in rows], "total": total, "page": page,
                "page_size": page_size, "total_pages": max(1, (total + page_size - 1) // page_size)}

    @staticmethod
    def serialize(row):
        return {key: (value.isoformat() if isinstance(value, datetime) else value)
                for key in ["name", "category", "source_file", "source_sheet", "source_row", "data",
                            "field_reviews", "is_validated", "validated_at", "validated_by", "revision"]
                for value in [getattr(row, key)]} | {"id": str(row.id)}

    async def record(self, category, identifier):
        row = (await self.session.execute(select(AssetInventoryRecord).where(
            AssetInventoryRecord.id == identifier, AssetInventoryRecord.category == category.value,
            AssetInventoryRecord.is_deleted.is_(False)))).scalar_one_or_none()
        if not row:
            raise LookupError("Inventory record not found.")
        return row

    def audit(self, row, action, actor, details):
        self.session.add(AssetInventoryAudit(category=row.category, record_id=str(row.id), action=action,
                                            actor=actor, details=details))

    async def create(self, category, body):
        batch = await self.ensure_source(category)
        data = [cell.model_dump() for cell in body.data]
        self.check_columns(data, batch.columns)
        order = (await self.session.execute(select(func.max(AssetInventoryRecord.source_order))
                 .where(AssetInventoryRecord.category == category.value))).scalar_one()
        identifier = uuid.uuid4()
        row = AssetInventoryRecord(id=identifier, category=category.value, source_key=f"manual:{identifier}",
              name=body.name, source_file="Manual entry", source_sheet=body.source_sheet,
              source_row=0, source_order=(order if order is not None else -1) + 1, data=data)
        self.session.add(row)
        await self.session.flush()
        self.audit(row, "create", body.actor, {"after": data})
        return self.serialize(row)

    @staticmethod
    def check_columns(data, columns):
        if len(data) != len(columns) or any(cell["index"] != index or cell["header"] != header
                                          for index, (cell, header) in enumerate(zip(data, columns))):
            raise ValueError("Workbook column order and labels cannot be changed.")

    async def change(self, category, identifier, body, action, field_index=None):
        row = await self.record(category, identifier)
        if row.revision != body.expected_revision:
            raise AssetReviewConflict("Inventory changed. Reload before editing or reviewing.")
        now = datetime.now(timezone.utc)
        reviews = dict(row.field_reviews)
        values = {"revision": row.revision + 1, "updated_at": now}
        before = {"name": row.name, "data": row.data, "field_reviews": dict(reviews)}
        if action == "edit":
            data = [cell.model_dump() for cell in body.data]
            self.check_columns(data, [cell["header"] for cell in row.data])
            for index, (original, changed) in enumerate(zip(row.data, data)):
                if original["value"] != changed["value"]:
                    reviews.pop(str(index), None)
            values.update(name=body.name, data=data)
        elif action in {"validate", "validate_field"}:
            if field_index is not None and not 0 <= field_index < len(row.data):
                raise ValueError("Field index is outside the workbook columns.")
            indexes = range(len(row.data)) if action == "validate" else [field_index]
            for index in indexes:
                cell = row.data[index]
                reviews[str(index)] = {"header": cell["header"], "value": cell["value"],
                                      "validated_at": now.isoformat(), "validated_by": body.actor}
        elif action == "delete":
            values.update(is_deleted=True)
        else:
            raise ValueError("Unsupported inventory action.")
        complete = len(reviews) == len(row.data)
        latest = max(reviews.values(), key=lambda review: review["validated_at"]) if reviews else None
        values.update(field_reviews=reviews, is_validated=complete,
                      validated_at=datetime.fromisoformat(latest["validated_at"]) if complete and latest else None,
                      validated_by=latest["validated_by"] if complete and latest else None)
        result = await self.session.execute(update(AssetInventoryRecord).where(
            AssetInventoryRecord.id == row.id, AssetInventoryRecord.revision == body.expected_revision,
            AssetInventoryRecord.is_deleted.is_(False)).values(**values).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise AssetReviewConflict("Inventory changed. Reload before editing or reviewing.")
        self.audit(row, action, body.actor, {"before": before, "after": {**values, "updated_at": now.isoformat(),
            "validated_at": values["validated_at"].isoformat() if values["validated_at"] else None}})
        await self.session.flush()
        await self.session.refresh(row)
        return self.serialize(row)
