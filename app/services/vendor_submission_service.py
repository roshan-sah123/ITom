"""Transactional vendor submission lifecycle and attachment validation."""

import base64
import hashlib
import io
import json
import warnings
from datetime import datetime, timezone

from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer
from starlette.concurrency import run_in_threadpool

from app.models.vendor import VendorSubmission
from frontend.vendor_management_server import clean_text, email_template, validate_sop

MAX_IMAGE = 1536 * 1024
MAX_BODY = 14 * 1024 * 1024


class AttachmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=150)
    data: str = Field(min_length=1, max_length=14 * 1024 * 1024)


class StepInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    what_to_do: str = Field(min_length=1, max_length=2000)
    how_to_do: str = Field(min_length=1, max_length=2000)
    image: AttachmentInput | None = None


class SubmissionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    vendor: str = Field(min_length=1, max_length=100)
    method: str = Field(min_length=1, max_length=80)
    steps: list[StepInput] = Field(min_length=1, max_length=30)
    sop: AttachmentInput | None = None
    expected_revision: int | None = Field(default=None, ge=1)


def validate_image(value: AttachmentInput) -> dict:
    name = clean_text(value.name, "Image filename", 150)
    if any(c in name for c in '/\\:<>"|?*') or name.startswith("."):
        raise ValueError("Image filename must be a simple filename.")
    if len(value.data) > ((MAX_IMAGE + 2) // 3) * 4:
        raise ValueError("Each screenshot must be at most 1.5 MiB.")
    try:
        data = base64.b64decode(value.data, validate=True)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Invalid image base64 data.") from exc
    if not 0 < len(data) <= MAX_IMAGE:
        raise ValueError("Each screenshot must contain 1 byte to 1.5 MiB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                format_name = image.format
                if format_name not in {"PNG", "JPEG", "WEBP"}:
                    raise ValueError("Screenshots must be PNG, JPEG or WebP.")
                if image.width * image.height > 16_000_000:
                    raise ValueError("Screenshots must not exceed 16 megapixels.")
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("Invalid or oversized screenshot image.") from exc
    extension = name.rsplit(".", 1)[-1].lower()
    if extension not in {"png": {"png"}, "jpeg": {"jpg", "jpeg"}, "webp": {"webp"}}[format_name.lower()]:
        raise ValueError("Screenshot extension must match its image content.")
    return {"name": name, "data": value.data, "mime": Image.MIME[format_name], "size": len(data)}


def validated_document(body: SubmissionInput) -> dict:
    steps = []
    for step in body.steps:
        texts = {
            key: email_template(getattr(step, key), label, 2000)
            for key, label in (("what_to_do", "What to do"), ("how_to_do", "How to do"))
        }
        if any(not text.strip() for text in texts.values()):
            raise ValueError("What to do and How to do are required for every step.")
        steps.append({**texts, "image": validate_image(step.image) if step.image else None})
    sop = validate_sop(body.sop.model_dump() if body.sop else None, download_only=True)
    return {
        "vendor": clean_text(body.vendor, "Vendor name", 100),
        "method": clean_text(body.method, "Method", 80),
        "steps": steps,
        "sop": {**body.sop.model_dump(), "mime": sop["mime"], "size": sop["size"]} if sop else None,
    }


def iso_time(value):
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


def summary(item: VendorSubmission) -> dict:
    return {
        "id": item.id, "vendor": item.vendor, "method": item.method,
        "step_count": item.step_count, "sop_name": item.sop_name,
        "revision": item.revision,
        "validation": "Validated" if item.validated_on else "Pending",
        "validated_by": item.validated_by, "validated_on": iso_time(item.validated_on),
        "created_at": iso_time(item.created_at),
    }


class VendorConflict(ValueError):
    pass


class VendorSubmissionService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, identifier: int, document=False):
        query = select(VendorSubmission).where(
            VendorSubmission.id == identifier, VendorSubmission.is_deleted.is_(False),
        ).execution_options(populate_existing=True)
        if document:
            query = query.options(undefer(VendorSubmission.document))
        item = await self.session.scalar(query)
        if item is None:
            raise LookupError("Vendor submission not found.")
        return item

    async def list(self, search: str, page: int, page_size: int):
        criteria = [VendorSubmission.is_deleted.is_(False)]
        if search:
            literal = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            criteria.append(VendorSubmission.vendor.ilike(f"%{literal}%", escape="\\"))
        total = await self.session.scalar(select(func.count()).select_from(VendorSubmission).where(*criteria))
        ranked = select(VendorSubmission.id, func.row_number().over(order_by=VendorSubmission.id).label("serial")
            ).where(VendorSubmission.is_deleted.is_(False)).subquery()
        items = (await self.session.execute(select(VendorSubmission, ranked.c.serial)
            .join(ranked, ranked.c.id == VendorSubmission.id).where(*criteria)
            .order_by(VendorSubmission.id).offset((page - 1) * page_size).limit(page_size))).all()
        next_serial = (await self.session.scalar(select(func.count()).select_from(VendorSubmission)
            .where(VendorSubmission.is_deleted.is_(False)))) + 1
        return {"items": [{**summary(item), "serial": serial} for item, serial in items],
                "total": total, "page": page, "page_size": page_size, "next_serial": next_serial}

    async def summarize(self, item):
        serial = await self.session.scalar(select(func.count()).select_from(VendorSubmission).where(
            VendorSubmission.is_deleted.is_(False), VendorSubmission.id <= item.id))
        return {**summary(item), "serial": serial}

    async def detail(self, identifier: int, include_files=False):
        item = await self.get(identifier, document=True)
        result = {
            **await self.summarize(item),
            "steps": [{
                "what_to_do": step["what_to_do"], "how_to_do": step["how_to_do"],
                "image": {"name": step["image"]["name"], "url": f"/api/v1/vendors/submissions/{identifier}/images/{index}"}
                if step["image"] else None,
            } for index, step in enumerate(item.document["steps"])],
            "sop": {"name": item.sop_name, "url": f"/api/v1/vendors/submissions/{identifier}/sop"} if item.sop_name else None,
        }
        if include_files:
            result["draft"] = {
                "vendor": item.vendor, "method": item.method,
                "steps": [{
                    "what_to_do": step["what_to_do"], "how_to_do": step["how_to_do"],
                    "image": {key: step["image"][key] for key in ("name", "data")} if step["image"] else None,
                } for step in item.document["steps"]],
            }
            result["sop_file"] = {key: item.document["sop"][key] for key in ("name", "data")} if item.document["sop"] else None
        return result

    async def create(self, body: SubmissionInput):
        document = await run_in_threadpool(validated_document, body)
        digest = hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest()
        previous = await self.session.scalar(select(VendorSubmission).where(VendorSubmission.request_id == body.request_id))
        if previous:
            if previous.is_deleted or previous.payload_hash != digest:
                raise VendorConflict("This submission request was already used. Refresh before submitting again.")
            return await self.summarize(previous)
        item = VendorSubmission(
            request_id=body.request_id, payload_hash=digest,
            vendor=document["vendor"], method=document["method"], document=document,
            step_count=len(document["steps"]), sop_name=document["sop"]["name"] if document["sop"] else None,
        )
        self.session.add(item)
        await self.session.flush()
        return await self.summarize(item)

    async def change(self, identifier: int, revision: int, values: dict):
        await self.get(identifier)
        result = await self.session.execute(update(VendorSubmission).where(
            VendorSubmission.id == identifier, VendorSubmission.revision == revision,
            VendorSubmission.is_deleted.is_(False),
        ).values(**values, revision=revision + 1, updated_at=datetime.now(timezone.utc)))
        if result.rowcount != 1:
            raise VendorConflict("Submission changed in another view. Refresh and try again.")

    async def edit(self, identifier: int, body: SubmissionInput):
        if body.expected_revision is None:
            raise ValueError("expected_revision is required when editing.")
        document = await run_in_threadpool(validated_document, body)
        await self.change(identifier, body.expected_revision, {
            "vendor": document["vendor"], "method": document["method"], "document": document,
            "step_count": len(document["steps"]), "sop_name": document["sop"]["name"] if document["sop"] else None,
            "validated_by": None, "validated_on": None,
        })
        return await self.summarize(await self.get(identifier))

    async def validate(self, identifier: int, reviewer: str, revision: int):
        await self.change(identifier, revision, {
            "validated_by": clean_text(reviewer, "Reviewer name", 128),
            "validated_on": datetime.now(timezone.utc),
        })
        return await self.summarize(await self.get(identifier))

    async def delete(self, identifier: int, revision: int):
        await self.change(identifier, revision, {"is_deleted": True, "document": {}, "sop_name": None})

    async def attachment(self, identifier: int, image_index: int | None = None):
        item = await self.get(identifier, document=True)
        if image_index is None:
            attachment = item.document["sop"]
        else:
            steps = item.document["steps"]
            attachment = steps[image_index]["image"] if 0 <= image_index < len(steps) else None
        if not attachment:
            raise LookupError("Attachment not found.")
        return attachment
