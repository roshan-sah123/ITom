"""Spreadsheet inventory reads and authenticated administrative actions."""

import asyncio
import hmac
import logging
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import SQLITE_DATABASE_PATH, create_sqlite_backup, get_db
from app.repositories.cmdb_inventory_repository import CMDBInventoryRepository
from app.services.cmdb_inventory_service import parse_inventory_workbook

logger = logging.getLogger("itom.cmdb_inventory")
router = APIRouter(prefix="/cmdb-inventory", tags=["Spreadsheet CMDB Inventory"])
InventoryType = Literal["server", "network", "telecom"]
MAX_WORKBOOK_BYTES = 25 * 1024 * 1024
BOOTSTRAP_FILES = {
    "server": Path(__file__).resolve().parents[4] / "data" / "bootstrap_server_inventory.xlsx",
    "network": Path(__file__).resolve().parents[4] / "data" / "bootstrap_network_inventory.xlsx",
}
_bootstrap_lock = asyncio.Lock()


class InventoryRecordUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=512)
    data: List[Dict[str, Any]]


class InventoryRecordCreate(InventoryRecordUpdate):
    inventory_type: InventoryType
    source_sheet: str = Field(min_length=1, max_length=255)


async def ensure_bootstrap_inventory(session: AsyncSession) -> None:
    """Seed a new authoritative database from bundled inventory workbooks once."""
    bind = session.get_bind()
    database_name = bind.url.database if bind is not None else None
    if not database_name or database_name == ":memory:":
        return
    try:
        if Path(database_name).resolve() != SQLITE_DATABASE_PATH:
            return
    except OSError:
        return
    async with _bootstrap_lock:
        repository = CMDBInventoryRepository(session)
        summary = await repository.summary()
        changed = False
        for inventory_type, workbook_path in BOOTSTRAP_FILES.items():
            count = int(summary.get(f"{inventory_type}_count", 0) or 0)
            if count > 0 or not workbook_path.is_file():
                continue
            content = await asyncio.to_thread(workbook_path.read_bytes)
            parsed = parse_inventory_workbook(content, inventory_type, workbook_path.name)
            await repository.replace_inventory(
                parsed, workbook_path.name, "Bundled Inventory Bootstrap", inventory_type
            )
            changed = True
        if changed:
            await session.commit()
            try:
                await asyncio.to_thread(create_sqlite_backup, SQLITE_DATABASE_PATH, "cmdb-bootstrap")
            except Exception as exc:
                logger.exception("Bootstrap inventory committed but backup creation failed: %s", exc)


async def require_inventory_admin(authorization: Optional[str] = Header(default=None)) -> str:
    # Temporary local-development access. Production stays locked until Entra role enforcement is added.
    if settings.ENVIRONMENT.strip().lower() != "production":
        return f"{settings.CMDB_INVENTORY_ADMIN_NAME} (Local development)"
    configured_token = settings.CMDB_INVENTORY_ADMIN_TOKEN
    if not configured_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CMDB inventory administration requires SSO or an admin token in production.",
        )
    scheme, separator, token = (authorization or "").partition(" ")
    if (not separator or scheme.casefold() != "bearer"
            or not hmac.compare_digest(token.strip(), configured_token)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin token is required.",
                            headers={"WWW-Authenticate": "Bearer"})
    return settings.CMDB_INVENTORY_ADMIN_NAME


@router.get("/summary")
async def inventory_summary(session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    await ensure_bootstrap_inventory(session)
    return await CMDBInventoryRepository(session).summary()


@router.get("/records")
async def list_inventory_records(
    inventory_type: Optional[InventoryType] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    search: Optional[str] = Query(None, max_length=200),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    await ensure_bootstrap_inventory(session)
    return await CMDBInventoryRepository(session).list_inventory(inventory_type, page, page_size, search)


@router.get("/admin/check")
async def check_inventory_admin(actor: str = Depends(require_inventory_admin)) -> Dict[str, str]:
    return {"admin": actor}


@router.post("/{inventory_type}/import", status_code=status.HTTP_200_OK)
async def replace_inventory_workbook(
    inventory_type: InventoryType,
    file: UploadFile = File(...),
    actor: str = Depends(require_inventory_admin),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    filename = Path(file.filename or "inventory.xlsx").name
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=415, detail="Upload an .xlsx workbook.")
    content = await file.read(MAX_WORKBOOK_BYTES + 1)
    if len(content) > MAX_WORKBOOK_BYTES:
        raise HTTPException(status_code=413, detail="Workbook exceeds the 25 MiB upload limit.")
    try:
        parsed = parse_inventory_workbook(content, inventory_type, filename)
        await CMDBInventoryRepository(session).replace_inventory(parsed, filename, actor, inventory_type)
        await session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    backup_path = None
    try:
        bind = session.get_bind()
        database_name = bind.url.database if bind is not None else None
        if database_name and database_name != ":memory:":
            backup_path = await asyncio.to_thread(create_sqlite_backup, Path(database_name), f"cmdb-{inventory_type}")
    except Exception as exc:
        logger.exception("Inventory import committed but backup creation failed: %s", exc)
    return {"inventory_type": inventory_type, "source_file": filename,
            "imported_count": len(parsed.records), "headers": parsed.headers,
            "backup_created": bool(backup_path)}


@router.post("/records", status_code=status.HTTP_201_CREATED)
async def create_inventory_record(
    payload: InventoryRecordCreate,
    actor: str = Depends(require_inventory_admin),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    try:
        return await CMDBInventoryRepository(session).create_record(
            payload.inventory_type, payload.source_sheet, payload.name, payload.data, actor
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put("/records/{record_id}")
async def edit_inventory_record(
    record_id: UUID,
    payload: InventoryRecordUpdate,
    actor: str = Depends(require_inventory_admin),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    try:
        record = await CMDBInventoryRepository(session).update_record(
            str(record_id), payload.name, payload.data, actor
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Inventory record not found.")
    return record


@router.post("/records/{record_id}/validate")
async def validate_inventory_record(
    record_id: UUID,
    actor: str = Depends(require_inventory_admin),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    record = await CMDBInventoryRepository(session).validate_record(str(record_id), actor)
    if record is None:
        raise HTTPException(status_code=404, detail="Inventory record not found.")
    return record


@router.post("/records/{record_id}/fields/{field_index}/validate")
async def validate_inventory_field(
    record_id: UUID,
    field_index: int,
    actor: str = Depends(require_inventory_admin),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    try:
        record = await CMDBInventoryRepository(session).validate_field(str(record_id), field_index, actor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Inventory record not found.")
    return record


@router.delete("/records/{record_id}")
async def delete_inventory_record(
    record_id: UUID,
    actor: str = Depends(require_inventory_admin),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    record = await CMDBInventoryRepository(session).delete_record(str(record_id), actor)
    if record is None:
        raise HTTPException(status_code=404, detail="Inventory record not found.")
    return {"deleted": True, "id": record["id"]}