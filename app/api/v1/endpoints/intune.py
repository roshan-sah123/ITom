"""Microsoft Intune telemetry and device compliance endpoints."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_ci_service
from app.core.config import settings
from app.core.database import get_db
from app.models.compliance_cache import IntuneComplianceReasonCache
from app.services.remediation_cache import remediation_cache_write_lock
from app.services.ci_service import CIService
from src.sync.graph_client import GraphApiError, GraphAuthError, GraphClient

router = APIRouter(prefix="/intune", tags=["Microsoft Intune Telemetry"])

ALLOWED_PAGE_SIZES = {10, 25, 50, 100}
_graph_client: Optional[GraphClient] = None


@router.get("/summary", status_code=status.HTTP_200_OK)
async def get_intune_summary(
    ci_service: CIService = Depends(get_ci_service),
) -> Dict[str, Any]:
    """Retrieve Microsoft Intune fleet telemetry, compliance reconciliation, and OS distribution."""
    summary = await ci_service.get_intune_summary()
    if summary.get("data_source") == "NONE":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No Configuration Items persisted for source system 'INTUNE'. Run a telemetry synchronization first.",
        )
    return summary


@router.get("/devices", status_code=status.HTTP_200_OK)
async def list_intune_devices(
    page: int = Query(1, ge=1),
    page_size: int = Query(25),
    search: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    vendor: Optional[str] = Query(None),
    sort_by: Optional[str] = Query("name"),
    sort_order: Optional[str] = Query("asc"),
    ci_service: CIService = Depends(get_ci_service),
) -> Dict[str, Any]:
    """Query paginated Microsoft Intune managed devices."""
    if page_size not in ALLOWED_PAGE_SIZES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"page_size must be one of {sorted(list(ALLOWED_PAGE_SIZES))}",
        )

    return await ci_service.get_cis_paginated(
        page=page,
        page_size=page_size,
        search=search,
        source_system="INTUNE",
        status=status_filter,
        vendor=vendor,
        sort_by=sort_by,
        sort_order=sort_order,
    )


def _get_graph_client() -> GraphClient:
    """Reuse one on-demand client so its valid Graph token stays cached."""
    global _graph_client
    if not all([settings.AZURE_TENANT_ID, settings.AZURE_CLIENT_ID, settings.AZURE_CLIENT_SECRET]):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Intune policy details are unavailable because the Microsoft Graph connection is not configured.",
        )
    if _graph_client is None:
        _graph_client = GraphClient(
            tenant_id=settings.AZURE_TENANT_ID,
            client_id=settings.AZURE_CLIENT_ID,
            client_secret=settings.AZURE_CLIENT_SECRET,
        )
    return _graph_client


def _require_session(session: Optional[AsyncSession]) -> AsyncSession:
    """Ensure the remediation cache is available before serving the worklist."""
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The remediation cache database is unavailable.",
        )
    return session


async def _upsert_reason_catalog(
    session: AsyncSession, reasons: List[Dict[str, Any]]
) -> List[IntuneComplianceReasonCache]:
    """Store the current Graph reason catalogue while preserving cached worklists."""
    now = datetime.now(timezone.utc)
    existing = list(
        (await session.execute(select(IntuneComplianceReasonCache))).scalars().all()
    )
    by_id = {record.summary_id: record for record in existing}
    for record in existing:
        record.is_active = False

    stored: List[IntuneComplianceReasonCache] = []
    for reason in reasons:
        summary_id = str(reason.get("id") or "")
        if not summary_id:
            continue
        record = by_id.get(summary_id)
        if record is None:
            record = IntuneComplianceReasonCache(
                summary_id=summary_id,
                setting_name=str(reason.get("setting_name") or "Unnamed setting"),
                platform=str(reason.get("platform") or "unknown"),
                noncompliant_count=int(reason.get("noncompliant_count") or 0),
                error_count=int(reason.get("error_count") or 0),
                conflict_count=int(reason.get("conflict_count") or 0),
                affected_count=int(reason.get("affected_count") or 0),
                devices=[],
                catalog_refreshed_at=now,
                is_active=True,
            )
            session.add(record)
        else:
            record.setting_name = str(reason.get("setting_name") or "Unnamed setting")
            record.platform = str(reason.get("platform") or "unknown")
            record.noncompliant_count = int(reason.get("noncompliant_count") or 0)
            record.error_count = int(reason.get("error_count") or 0)
            record.conflict_count = int(reason.get("conflict_count") or 0)
            record.affected_count = int(reason.get("affected_count") or 0)
            record.catalog_refreshed_at = now
            record.is_active = True
        stored.append(record)

    await session.flush()
    return stored


@router.get("/noncompliance-reasons", status_code=status.HTTP_200_OK)
async def list_noncompliance_reasons(
    session: Optional[AsyncSession] = Depends(get_db),
) -> Dict[str, Any]:
    """Serve the cached Intune compliance setting catalogue."""
    db = _require_session(session)
    cached = list(
        (
            await db.execute(
                select(IntuneComplianceReasonCache)
                .where(IntuneComplianceReasonCache.is_active.is_(True))
                .order_by(
                    IntuneComplianceReasonCache.setting_name,
                    IntuneComplianceReasonCache.platform,
                )
            )
        ).scalars().all()
    )
    if not cached:
        try:
            reasons = await asyncio.to_thread(
                _get_graph_client().get_noncompliance_reason_summaries
            )
        except (GraphApiError, GraphAuthError):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Intune compliance reasons could not be retrieved. Confirm that the app can read Intune compliance configuration.",
            )
        async with remediation_cache_write_lock:
            cached = await _upsert_reason_catalog(db, reasons)
    return {
        "source": "DATABASE",
        "items": [record.to_reason() for record in cached],
        "total": len(cached),
    }


@router.get("/noncompliance-reasons/{summary_id}/devices", status_code=status.HTTP_200_OK)
async def list_devices_by_noncompliance_reason(
    summary_id: str,
    session: Optional[AsyncSession] = Depends(get_db),
) -> Dict[str, Any]:
    """Serve the cached affected-device worklist for one Intune setting."""
    db = _require_session(session)
    cached = await db.get(IntuneComplianceReasonCache, summary_id)
    if cached is None or not cached.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This compliance setting is not present in the cached Intune reason catalogue.",
        )

    if cached.worklist_refreshed_at is None:
        # End the read transaction before the long Graph call. This prevents a
        # stale SQLite reader from blocking the cache writer that follows.
        await db.rollback()
        try:
            devices = await asyncio.to_thread(
                _get_graph_client().get_noncompliant_devices_for_reason, summary_id
            )
        except (GraphApiError, GraphAuthError):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Devices for this Intune compliance reason could not be retrieved.",
            )
        async with remediation_cache_write_lock:
            # Another browser request may have filled the cache while this
            # request was retrieving Graph evidence. Keep the saved version.
            cached = await db.get(
                IntuneComplianceReasonCache,
                summary_id,
                populate_existing=True,
            )
            if cached is None or not cached.is_active:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="This compliance setting is not present in the cached Intune reason catalogue.",
                )
            if cached.worklist_refreshed_at is None:
                cached.devices = devices
                cached.worklist_refreshed_at = datetime.now(timezone.utc)
                await db.flush()

    return {
        "source": "DATABASE",
        "cached_at": cached.worklist_refreshed_at.isoformat(),
        "items": cached.devices,
        "total": len(cached.devices),
    }


@router.get("/devices/{ci_id}/compliance-details", status_code=status.HTTP_200_OK)
async def get_device_compliance_details(
    ci_id: str,
    ci_service: CIService = Depends(get_ci_service),
) -> Dict[str, Any]:
    """Retrieve source-backed compliance policy evidence for one selected device."""
    device = await ci_service.get_ci_by_id(ci_id)
    if not device or device.get("source_system") != "INTUNE":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Intune device not found.")

    compliance_state = str(device.get("status") or "Unknown")
    if compliance_state.lower() == "compliant":
        return {
            "device": {
                "id": str(device.get("id")),
                "name": device.get("name"),
                "compliance_state": compliance_state,
            },
            "reason": "This device is currently reported as compliant.",
            "policies": [],
            "noncompliant_policy_count": 0,
            "failing_setting_count": 0,
        }

    try:
        graph = _get_graph_client()
        evidence = graph.get_device_compliance_policy_states(str(device.get("source_id")))
    except (GraphApiError, GraphAuthError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Intune policy details could not be retrieved for this device. Confirm that the app has permission to read Intune compliance policy states.",
        )

    return {
        "device": {
            "id": str(device.get("id")),
            "name": device.get("name"),
            "compliance_state": compliance_state,
        },
        "reason": "Policy and setting details were retrieved on demand from Intune.",
        **evidence,
    }
