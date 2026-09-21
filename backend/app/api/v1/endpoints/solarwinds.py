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
    summary = await ci_service.get_solarwinds_summary()
    if summary.get("data_source") == "NONE":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No Configuration Items persisted for source system 'SOLARWINDS'. Run a telemetry synchronization first.",
        )
    return summary


@router.get("/nodes", status_code=status.HTTP_200_OK)
async def list_solarwinds_nodes(
    page: int = Query(1, ge=1),
    page_size: int = Query(25),
    search: Optional[str] = Query(None),
    health_tier: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    location: Optional[str] = Query(None, description="Exact SolarWinds site location"),
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
        location=location,
        vendor=vendor,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/sites", status_code=status.HTTP_200_OK)
async def list_solarwinds_sites(
    ci_service: CIService = Depends(get_ci_service),
) -> Dict[str, Any]:
    """Retrieve 60-campus location telemetry breakdown, health tiers, and sparkline trends."""
    sites = await ci_service.get_solarwinds_sites()
    return {
        "status": "success",
        "data": {
            "total_sites": len(sites),
            "items": sites,
        }
    }


@router.get("/sites/{site_id}/trend", status_code=status.HTTP_200_OK)
async def get_solarwinds_site_trend(
    site_id: str,
    hours: int = Query(24, ge=1, le=168),
    ci_service: CIService = Depends(get_ci_service),
) -> Dict[str, Any]:
    """Retrieve time-series availability and latency trend history for a specific campus facility."""
    trend = await ci_service.get_solarwinds_site_trend(site_id, hours=hours)
    return {
        "status": "success",
        "data": trend,
    }
