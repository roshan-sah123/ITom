"""Workbook-backed inventory with local, independently persisted CMDB reviews."""

import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.api.v1.endpoints.module_access import require_local_module, require_inventory_key
from app.core.config import settings
from app.core.database import get_module_db
from app.services.asset_review_service import AssetReviewConflict, AssetReviewService
from app.services.asset_inventory_service import (
    AssetInventoryCategory,
    AssetInventoryService,
    AssetInventoryUnavailable,
)
from frontend.vendor_management_server import reject_constant, unique_object

def local_inventory(request: Request):
    require_local_module(request, "CMDB inventory")


router = APIRouter(prefix="/assets", tags=["Asset inventory"], dependencies=[Depends(local_inventory)])
logger = logging.getLogger("itom.assets")


async def operation(awaitable, session):
    try:
        result = await awaitable
        await session.commit()
        return result
    except AssetInventoryUnavailable as error:
        await session.rollback()
        return JSONResponse(status_code=503, content={"detail": str(error), "data_available": False})
    except (AssetReviewConflict, IntegrityError) as error:
        await session.rollback()
        if isinstance(error, IntegrityError):
            logger.exception("Conflicting CMDB inventory transaction")
        raise HTTPException(409, "Inventory changed or is being initialized. Reload and retry.") from error
    except LookupError as error:
        await session.rollback()
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        await session.rollback()
        raise HTTPException(422, str(error)) from error
    except SQLAlchemyError as error:
        await session.rollback()
        logger.exception("CMDB inventory datastore failed")
        raise HTTPException(503, "CMDB inventory datastore unavailable. No changes were saved.") from error


def get_asset_inventory_service() -> AssetInventoryService:
    return AssetInventoryService(settings.ASSET_INVENTORY_DIR)


@router.get("/summary", status_code=status.HTTP_200_OK)
async def get_asset_inventory_summary(
    service: AssetInventoryService = Depends(get_asset_inventory_service),
    session=Depends(get_module_db),
) -> dict:
    return await operation(AssetReviewService(session, service).summary(), session)


@router.get("/inventory/{category}", status_code=status.HTTP_200_OK)
async def list_asset_inventory(
    category: AssetInventoryCategory,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    search: str | None = Query(None, max_length=200),
    service: AssetInventoryService = Depends(get_asset_inventory_service),
    session=Depends(get_module_db),
) -> dict:
    if page_size not in {10, 25, 50, 100, 150, 200}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="page_size must be one of [10, 25, 50, 100, 150, 200]",
        )
    result = await operation(AssetReviewService(session, service).list(category, page, page_size, search or ""), session)
    if isinstance(result, JSONResponse):
        return result
    return {**result, "items": [{cell["header"]: cell["value"] for cell in row["data"]} for row in result["items"]]}


def inventory_admin(request: Request):
    require_inventory_key(request, "CMDB inventory")


class InventoryActor(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)
    actor: str = Field(min_length=1, max_length=128)


class InventoryReview(InventoryActor):
    expected_revision: int = Field(ge=1, strict=True)


class InventoryCell(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)
    index: int = Field(ge=0)
    header: str = Field(min_length=1, max_length=255)
    value: str | int | float | bool | None

    @field_validator("value")
    @classmethod
    def value_length(cls, value):
        if isinstance(value, str) and len(value) > 10000:
            raise ValueError("Inventory values may contain at most 10,000 characters.")
        return value


class InventoryCreate(InventoryActor):
    name: str = Field(min_length=1, max_length=512)
    source_sheet: str = Field(min_length=1, max_length=255)
    data: list[InventoryCell] = Field(min_length=1, max_length=200)


class InventoryEdit(InventoryReview):
    name: str = Field(min_length=1, max_length=512)
    data: list[InventoryCell] = Field(min_length=1, max_length=200)


async def bounded_body(request: Request, schema):
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise HTTPException(415, "Send application/json.")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 256 * 1024:
            raise HTTPException(413, "Inventory request exceeds 256 KiB.")
    try:
        return schema.model_validate(json.loads(raw.decode("utf-8"), parse_constant=reject_constant, object_pairs_hook=unique_object))
    except (ValidationError, ValueError, UnicodeError, RecursionError) as error:
        raise HTTPException(422, "Provide valid inventory fields, an operator name and a current revision.") from error


async def create_body(request: Request):
    return await bounded_body(request, InventoryCreate)


async def edit_body(request: Request):
    return await bounded_body(request, InventoryEdit)


async def review_body(request: Request):
    return await bounded_body(request, InventoryReview)


@router.get("/admin/check", dependencies=[Depends(inventory_admin)])
async def check_admin():
    return {"enabled": True, "identity": "self-reported"}


@router.get("/records/{category}", dependencies=[Depends(local_inventory)])
async def inventory_records(category: AssetInventoryCategory, page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200), search: str = Query("", max_length=200),
    service=Depends(get_asset_inventory_service), session=Depends(get_module_db)):
    return await operation(AssetReviewService(session, service).list(category, page, page_size, search), session)


@router.post("/records/{category}", status_code=201, dependencies=[Depends(local_inventory)])
async def create_record(category: AssetInventoryCategory, body=Depends(create_body),
    service=Depends(get_asset_inventory_service), session=Depends(get_module_db)):
    return await operation(AssetReviewService(session, service).create(category, body), session)


@router.put("/records/{category}/{identifier}", dependencies=[Depends(inventory_admin)])
async def edit_record(category: AssetInventoryCategory, identifier: UUID, body=Depends(edit_body),
    service=Depends(get_asset_inventory_service), session=Depends(get_module_db)):
    return await operation(AssetReviewService(session, service).change(category, identifier, body, "edit"), session)


@router.post("/records/{category}/{identifier}/validate", dependencies=[Depends(inventory_admin)])
async def validate_record(category: AssetInventoryCategory, identifier: UUID, body=Depends(review_body),
    service=Depends(get_asset_inventory_service), session=Depends(get_module_db)):
    return await operation(AssetReviewService(session, service).change(category, identifier, body, "validate"), session)


@router.post("/records/{category}/{identifier}/fields/{field_index}/validate", dependencies=[Depends(inventory_admin)])
async def validate_field(category: AssetInventoryCategory, identifier: UUID, field_index: int, body=Depends(review_body),
    service=Depends(get_asset_inventory_service), session=Depends(get_module_db)):
    return await operation(AssetReviewService(session, service).change(category, identifier, body, "validate_field", field_index), session)


@router.delete("/records/{category}/{identifier}", status_code=204, dependencies=[Depends(inventory_admin)])
async def delete_record(category: AssetInventoryCategory, identifier: UUID, body=Depends(review_body),
    service=Depends(get_asset_inventory_service), session=Depends(get_module_db)):
    result = await operation(AssetReviewService(session, service).change(category, identifier, body, "delete"), session)
    return result if isinstance(result, JSONResponse) else Response(status_code=204)
