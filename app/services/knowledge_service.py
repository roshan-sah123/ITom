import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import undefer
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.models.knowledge import KnowledgeContent
from app.services.vendor_submission_service import VendorConflict, iso_time
from frontend.vendor_management_server import clean_text

MAX_FILE = 5 * 1024 * 1024
ALLOWED_EXTENSIONS = {".docx", ".pdf", ".pptx", ".txt", ".mp4", ".webm", ".mov"}


class KnowledgeFileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=150)
    type: str = Field(max_length=120)
    data: str = Field(min_length=1, max_length=7 * 1024 * 1024)


class KnowledgeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=4000)
    category: str = Field(min_length=1, max_length=100)
    file: KnowledgeFileInput | None = None
    request_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    expected_revision: int | None = Field(default=None, ge=1, strict=True)


def validate_file(file: KnowledgeFileInput):
    name = clean_text(file.name, "Filename", 150)
    if any(char in name for char in '/\\:<>"|?*') or name.startswith(".") or name.endswith((".", " ")):
        raise ValueError("Use a simple filename without path characters.")
    if Path(name).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError("Choose DOCX, PDF, PPTX, TXT or an MP4, WebM or MOV video. Excel files are not supported.")
    if len(file.data) > ((MAX_FILE + 2) // 3) * 4:
        raise ValueError("Knowledge files must be at most 5 MiB.")
    try:
        raw = base64.b64decode(file.data, validate=True)
    except (ValueError, UnicodeError) as error:
        raise ValueError("Invalid file base64 content.") from error
    if not 0 < len(raw) <= MAX_FILE:
        raise ValueError("Knowledge files must be non-empty and at most 5 MiB.")
    return {"file_name": name, "file_type": "application/octet-stream", "file_size": len(raw), "file_data": raw}


class KnowledgeService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, identifier: int, file: bool = False) -> KnowledgeContent:
        query = select(KnowledgeContent).where(KnowledgeContent.id == identifier, KnowledgeContent.is_deleted.is_(False))
        if file:
            query = query.options(undefer(KnowledgeContent.file_data))
        row = await self.session.scalar(query.execution_options(populate_existing=True))
        if not row:
            raise LookupError("Knowledge content not found.")
        return row

    async def summary(self, row: KnowledgeContent, serial: int | None = None):
        if serial is None:
            serial = await self.session.scalar(select(func.count()).select_from(KnowledgeContent).where(
                KnowledgeContent.is_deleted.is_(False), KnowledgeContent.id <= row.id))
        return {"id": str(row.id), "serial": serial, "revision": row.revision,
                "name": row.name, "description": row.description, "category": row.category,
                "file": {"name": row.file_name, "type": row.file_type, "size": row.file_size,
                         "url": f"/api/v1/knowledge/content/{row.id}/file"},
                "validatedOn": iso_time(row.validated_on), "validatedBy": row.validated_by or ""}

    async def list(self, page, page_size):
        criteria = KnowledgeContent.is_deleted.is_(False)
        total = await self.session.scalar(select(func.count()).select_from(KnowledgeContent).where(criteria))
        ranked = select(KnowledgeContent.id, func.row_number().over(order_by=KnowledgeContent.id).label("serial")
            ).where(criteria).subquery()
        rows = (await self.session.execute(select(KnowledgeContent, ranked.c.serial)
                .join(ranked, ranked.c.id == KnowledgeContent.id).order_by(KnowledgeContent.id)
                .offset((page - 1) * page_size).limit(page_size))).all()
        return {"items": [await self.summary(row, serial) for row, serial in rows], "total": total, "page": page,
                "page_size": page_size, "total_pages": max(1, (total + page_size - 1) // page_size)}

    async def create(self, body: KnowledgeInput):
        if not body.request_id or not body.file or body.expected_revision is not None:
            raise ValueError("Creation requires request_id and a file.")
        file = await run_in_threadpool(validate_file, body.file)
        digest = hashlib.sha256(json.dumps({
            "name": body.name, "description": body.description, "category": body.category,
            "file": {**file, "file_data": hashlib.sha256(file["file_data"]).hexdigest()},
        }, sort_keys=True).encode()).hexdigest()
        previous = await self.session.scalar(select(KnowledgeContent).where(KnowledgeContent.request_id == body.request_id))
        if previous:
            if previous.is_deleted or previous.payload_hash != digest:
                raise VendorConflict("This creation request was already used. Reload before retrying.")
            return await self.summary(previous)
        row = KnowledgeContent(request_id=body.request_id, payload_hash=digest, name=body.name,
                               description=body.description, category=body.category, **file)
        self.session.add(row)
        await self.session.flush()
        return await self.summary(row)

    async def change(self, identifier, revision, values):
        await self.get(identifier)
        result = await self.session.execute(update(KnowledgeContent).where(
            KnowledgeContent.id == identifier, KnowledgeContent.revision == revision,
            KnowledgeContent.is_deleted.is_(False)).values(**values, revision=revision + 1,
                updated_at=datetime.now(timezone.utc)).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise VendorConflict("Content changed in another view. Reload before editing or reviewing.")

    async def edit(self, identifier: int, body: KnowledgeInput):
        if body.expected_revision is None or body.request_id is not None:
            raise ValueError("Editing requires expected_revision.")
        values = {"name": body.name, "description": body.description, "category": body.category,
                  "validated_by": None, "validated_on": None}
        if body.file:
            values.update(await run_in_threadpool(validate_file, body.file))
        await self.change(identifier, body.expected_revision, values)
        return await self.summary(await self.get(identifier))

    async def validate(self, identifier, body):
        reviewer = clean_text(body.reviewer, "Reviewer", 128)
        await self.change(identifier, body.expected_revision, {"validated_by": reviewer,
                          "validated_on": datetime.now(timezone.utc)})
        return await self.summary(await self.get(identifier))

    async def delete(self, identifier, revision):
        await self.change(identifier, revision, {"is_deleted": True, "file_data": b"", "file_size": 0})
