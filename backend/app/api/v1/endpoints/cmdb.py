"""CMDB REST API endpoints for Configuration Items, filtering, and topology relationships."""

import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from app.api.deps import get_ci_service
from app.services.ci_service import CIService

router = APIRouter(prefix="/cmdb", tags=["CMDB Configuration Items"])

ALLOWED_PAGE_SIZES = {10, 25, 50, 100}


@router.get("/summary", status_code=status.HTTP_200_OK)
async def get_cmdb_summary(
    ci_service: CIService = Depends(get_ci_service),
) -> Dict[str, Any]:
    """Retrieve aggregated fleet summary, health distribution, and role distribution."""
    return await ci_service.get_cmdb_summary()


@router.get("/cis", status_code=status.HTTP_200_OK)
async def list_configuration_items(
    page: int = Query(1, ge=1, description="1-based page number"),
    page_size: int = Query(25, description="Allowed: 10, 25, 50, 100"),
    search: Optional[str] = Query(None, description="Search term for name, IP, serial, vendor"),
    source_system: Optional[str] = Query(None, description="SOLARWINDS or INTUNE"),
    ci_type: Optional[str] = Query(None, description="Filter by CI Type classification"),
    vendor: Optional[str] = Query(None, description="Filter by vendor / manufacturer"),
    health_tier: Optional[str] = Query(None, description="High, Medium, or Low"),
    status_filter: Optional[str] = Query(None, alias="status", description="Operational status filter"),
    sort_by: Optional[str] = Query("name", description="Column to sort by"),
    sort_order: Optional[str] = Query("asc", description="asc or desc"),
    ci_service: CIService = Depends(get_ci_service),
) -> Dict[str, Any]:
    """Query paginated Configuration Items with sub-20ms multi-column filtering."""
    if page_size not in ALLOWED_PAGE_SIZES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"page_size must be one of {sorted(list(ALLOWED_PAGE_SIZES))}",
        )

    return await ci_service.get_cis_paginated(
        page=page,
        page_size=page_size,
        search=search,
        source_system=source_system,
        ci_type=ci_type,
        vendor=vendor,
        health_tier=health_tier,
        status=status_filter,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/cis/{ci_id}", status_code=status.HTTP_200_OK)
async def get_configuration_item_by_id(
    ci_id: str,
    ci_service: CIService = Depends(get_ci_service),
) -> Any:
    """Retrieve details for a single Configuration Item by UUID."""
    ci = await ci_service.get_ci_by_id(ci_id)
    if not ci:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": "Configuration Item not found", "id": ci_id},
        )
    return ci


@router.get("/cis/{ci_id}/history", status_code=status.HTTP_200_OK)
async def get_configuration_item_history(
    ci_id: str,
    limit: int = Query(50, ge=1, le=500),
    ci_service: CIService = Depends(get_ci_service),
) -> List[Any]:
    """Retrieve time-series status and health transitions for a CI."""
    return await ci_service.get_ci_history(ci_id, limit=limit)


@router.get("/cis/{ci_id}/relationships", status_code=status.HTTP_200_OK)
async def get_configuration_item_relationships(
    ci_id: str,
    ci_service: CIService = Depends(get_ci_service),
) -> List[Any]:
    """Retrieve dependency and topological graph edges for a CI."""
    return await ci_service.get_ci_relationships(ci_id)
