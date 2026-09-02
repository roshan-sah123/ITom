"""SolarWinds Orion SWIS telemetry and server node endpoints."""

from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_ci_service
from app.services.ci_service import CIService

router = APIRouter(prefix="/solarwinds", tags=["SolarWinds Telemetry"])

ALLOWED_PAGE_SIZES = {10, 25, 50, 100}


@router.get("/summary", status_code=status.HTTP_200_OK)
async def get_solarwinds_summary(
    ci_service: CIService = Depends(get_ci_service),
) -> Dict[str, Any]:
    """Retrieve SolarWinds Orion server node metrics, health tier distributions, and performance averages."""
    return await ci_service.get_solarwinds_summary()


@router.get("/nodes", status_code=status.HTTP_200_OK)
async def list_solarwinds_nodes(
    page: int = Query(1, ge=1),
    page_size: int = Query(25),
    search: Optional[str] = Query(None),
    health_tier: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    vendor: Optional[str] = Query(None),
    sort_by: Optional[str] = Query("name"),
    sort_order: Optional[str] = Query("asc"),
    ci_service: CIService = Depends(get_ci_service),
) -> Dict[str, Any]:
    """Query paginated SolarWinds Orion server nodes."""
    if page_size not in ALLOWED_PAGE_SIZES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"page_size must be one of {sorted(list(ALLOWED_PAGE_SIZES))}",
        )

    return await ci_service.get_cis_paginated(
        page=page,
        page_size=page_size,
        search=search,
        source_system="SOLARWINDS",
        health_tier=health_tier,
        status=status_filter,
        vendor=vendor,
        sort_by=sort_by,
        sort_order=sort_order,
    )
