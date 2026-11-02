import base64
import hashlib
import io
import json
import unicodedata
import warnings
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import undefer
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.models.knowledge import KnowledgeContent
from app.services.vendor_submission_service import VendorConflict, iso_time
from frontend.vendor_management_server import clean_text, safe_xml, validate_sop

MAX_FILE = 5 * 1024 * 1024
FORMATS = {
    ".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".txt": "text/plain", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
}


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
    extension = Path(name).suffix.lower()
    mime = FORMATS.get(extension)
    if not mime or mime != file.type:
        raise ValueError("Unsupported file format or mismatched MIME type.")
    if len(file.data) > ((MAX_FILE + 2) // 3) * 4:
        raise ValueError("Knowledge files must be at most 5 MiB.")
    try:
        raw = base64.b64decode(file.data, validate=True)
    except (ValueError, UnicodeError) as error:
        raise ValueError("Invalid file base64 content.") from error
    if not 0 < len(raw) <= MAX_FILE:
        raise ValueError("Knowledge files must be non-empty and at most 5 MiB.")
    if extension in {".pdf", ".docx", ".txt"}:
        validate_sop({"name": name, "data": file.data}, download_only=True)
    elif mime.startswith("image/"):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw)) as image:
                    if Image.MIME.get(image.format) != mime or image.width * image.height > 16_000_000:
                        raise ValueError("Image content must match its extension and be at most 16 megapixels.")
                    image.verify()
                with Image.open(io.BytesIO(raw)) as image:
                    image.load()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
            raise ValueError("Invalid image content.") from error
    elif extension in {".xlsx", ".pptx"}:
        try:
            with ZipFile(io.BytesIO(raw)) as archive:
                entries = archive.infolist()
                names = {entry.filename for entry in entries}
                required = "xl/workbook.xml" if extension == ".xlsx" else "ppt/presentation.xml"
                if (required not in names or "[Content_Types].xml" not in names or len(entries) > 2000
                        or len({name.casefold() for name in names}) != len(entries)):
                    raise ValueError("Invalid Office document structure.")
                if sum(entry.file_size for entry in entries) > 30 * 1024 * 1024:
                    raise ValueError("Expanded Office document exceeds 30 MiB.")
                for entry in entries:
                    if (entry.flag_bits & 1 or entry.filename.startswith("/") or ".." in PurePosixPath(entry.filename).parts
                            or "\\" in entry.filename or ":" in entry.filename
                            or any(unicodedata.category(char).startswith("C") for char in entry.filename)):
                        raise ValueError("Unsafe Office archive.")
                    if any(marker in entry.filename.lower() for marker in ("vbaproject", "activex", "embeddings", "externallinks")):
                        raise ValueError("Active or embedded Office content is not supported.")
                    if entry.filename.endswith((".xml", ".rels")):
                        with archive.open(entry) as stream:
                            data = stream.read(10 * 1024 * 1024 + 1)
                            if len(data) > 10 * 1024 * 1024 or stream.read(1):
                                raise ValueError("Office XML entry exceeds 10 MiB.")
                        root = safe_xml(data)
                        if b"macroenabled" in data.lower():
                            raise ValueError("Macro-enabled Office content is not supported.")
                        if entry.filename.endswith(".rels"):
                            for relation in root:
                                if relation.get("TargetMode", "Internal") != "Internal":
                                    raise ValueError("External Office content is not supported.")
                        if entry.filename == required:
                            expected = ("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}workbook"
                                        if extension == ".xlsx" else
                                        "{http://schemas.openxmlformats.org/presentationml/2006/main}presentation")
                            if root.tag != expected:
                                raise ValueError("Invalid Office document root.")
        except (BadZipFile, RuntimeError, NotImplementedError, OSError) as error:
            raise ValueError("Invalid Office file.") from error
    elif extension == ".webm":
        if not raw.startswith(b"\x1a\x45\xdf\xa3") or b"webm" not in raw[:4096]:
            raise ValueError("Invalid WebM file header.")
    elif extension in {".mp4", ".mov"}:
        size = int.from_bytes(raw[:4], "big")
        markers = {b"ftyp"} if extension == ".mp4" else {b"ftyp", b"moov", b"mdat", b"wide", b"free"}
        if len(raw) < 12 or raw[4:8] not in markers or (size not in {0, 1} and (size < 8 or size > len(raw))):
            raise ValueError("Invalid video container header.")
    return {"file_name": name, "file_type": mime, "file_size": len(raw), "file_data": raw}


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
