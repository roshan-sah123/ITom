"""Microsoft Intune telemetry and device compliance endpoints."""

from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_ci_service
from app.services.ci_service import CIService

router = APIRouter(prefix="/intune", tags=["Microsoft Intune Telemetry"])

ALLOWED_PAGE_SIZES = {10, 25, 50, 100}


@router.get("/summary", status_code=status.HTTP_200_OK)
async def get_intune_summary(
    ci_service: CIService = Depends(get_ci_service),
) -> Dict[str, Any]:
    """Retrieve Microsoft Intune fleet telemetry, compliance reconciliation, and OS distribution."""
    return await ci_service.get_intune_summary()


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
