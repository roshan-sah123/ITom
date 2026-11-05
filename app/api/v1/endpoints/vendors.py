"""Same-origin, local-only vendor management until portal sign-in is available."""

import base64
import json
import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app.api.v1.endpoints.module_access import require_local_module, require_inventory_key
from app.core.database import get_module_db
from app.services.vendor_submission_service import (
    MAX_BODY, SubmissionInput, VendorConflict, VendorSubmissionService,
)
from frontend.vendor_management_server import reject_constant, unique_object
from app.services.attachment_preview import PreviewError, preview_attachment

logger = logging.getLogger("itom.vendors")


def require_local_vendor(request: Request):
    require_local_module(request, "Vendor management")


def vendor_admin(request: Request):
    require_inventory_key(request, "Vendor management")


router = APIRouter(
    prefix="/vendors/submissions", tags=["Vendor submissions"],
    dependencies=[Depends(require_local_vendor)],
)


async def submission_body(request: Request):
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise HTTPException(415, "Send application/json.")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_BODY:
            raise HTTPException(413, "Submission exceeds 14 MiB; use smaller screenshots or SOP.")
    try:
        value = json.loads(raw.decode("utf-8"), parse_constant=reject_constant, object_pairs_hook=unique_object)
        return SubmissionInput.model_validate(value)
    except ValidationError as exc:
        raise HTTPException(422, "Invalid submission. Provide vendor, method, 1–30 complete steps and valid attachments.") from exc
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise HTTPException(422, "Invalid UTF-8 JSON submission.") from exc


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reviewer: str = Field(min_length=1, max_length=128)
    expected_revision: int = Field(ge=1)


async def operation(awaitable, session, write=False, label="Vendor"):
    try:
        result = await awaitable
        if write:
            await session.commit()
        return result
    except VendorConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except IntegrityError as exc:
        await session.rollback()
        logger.exception("Conflicting %s transaction", label)
        raise HTTPException(409, f"A conflicting {label.lower()} submission was saved. Refresh and retry.") from exc
    except SQLAlchemyError as exc:
        await session.rollback()
        logger.exception("%s datastore operation failed", label)
        raise HTTPException(503, f"{label} datastore unavailable. No changes were saved; retry safely.") from exc


@router.get("")
async def list_submissions(
    search: str = Query("", max_length=200), page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100), session=Depends(get_module_db),
):
    return await operation(VendorSubmissionService(session).list(search.strip(), page, page_size), session)


@router.post("", status_code=201)
async def create_submission(body=Depends(submission_body), session=Depends(get_module_db)):
    return await operation(VendorSubmissionService(session).create(body), session, write=True)


@router.get("/{identifier}")
async def submission_detail(identifier: int, include_files: bool = False, session=Depends(get_module_db)):
    return await operation(VendorSubmissionService(session).detail(identifier, include_files), session)


@router.put("/{identifier}", dependencies=[Depends(vendor_admin)])
async def edit_submission(identifier: int, body=Depends(submission_body), session=Depends(get_module_db)):
    return await operation(VendorSubmissionService(session).edit(identifier, body), session, write=True)


@router.post("/{identifier}/validate", dependencies=[Depends(vendor_admin)])
async def validate_submission(identifier: int, body: ReviewInput, session=Depends(get_module_db)):
    return await operation(
        VendorSubmissionService(session).validate(identifier, body.reviewer, body.expected_revision), session, write=True,
    )


@router.delete("/{identifier}", status_code=204, dependencies=[Depends(vendor_admin)])
async def delete_submission(identifier: int, expected_revision: int = Query(..., ge=1), session=Depends(get_module_db)):
    await operation(VendorSubmissionService(session).delete(identifier, expected_revision), session, write=True)
    return Response(status_code=204)


def file_response(attachment, image=False, raw=None, download_only=True):
    return Response(
        content=raw if raw is not None else base64.b64decode(attachment["data"]),
        media_type="application/octet-stream" if download_only and not image else attachment["mime"],
        headers={
            "Content-Disposition": ("inline" if image else "attachment")
            + "; filename*=UTF-8''" + quote(attachment["name"], safe=""),
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        },
    )


async def attachment_preview_response(name: str, raw: bytes):
    try:
        content, mime = await run_in_threadpool(preview_attachment, name, raw)
    except PreviewError as error:
        raise HTTPException(error.status_code, str(error)) from error
    return Response(content, media_type=mime, headers={
        "Content-Disposition": "inline",
        "Content-Security-Policy": "default-src 'none'; sandbox",
        "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store",
    })


@router.get("/{identifier}/sop")
async def download_sop(identifier: int, preview: bool = Query(False), session=Depends(get_module_db)):
    attachment = await operation(VendorSubmissionService(session).attachment(identifier), session)
    if preview:
        return await attachment_preview_response(attachment["name"], base64.b64decode(attachment["data"]))
    return file_response(attachment)


@router.get("/{identifier}/images/{image_index}")
async def step_image(identifier: int, image_index: int, session=Depends(get_module_db)):
    attachment = await operation(VendorSubmissionService(session).attachment(identifier, image_index), session)
    return file_response(attachment, image=True)
