"""Telemetry synchronization management, audit history, and trigger endpoints."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from app.api.deps import get_sync_repository, get_sync_service
from app.repositories.sync_repository import SyncRepository
from app.services.sync_service import SyncService

router = APIRouter(prefix="/sync", tags=["Telemetry Sync Engine"])


@router.get("/runs", status_code=status.HTTP_200_OK)
async def list_sync_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sync_repo: SyncRepository = Depends(get_sync_repository),
) -> List[Any]:
    """Retrieve audit history of background telemetry synchronization runs."""
    return await sync_repo.get_sync_runs_paginated(page=page, page_size=page_size)


@router.get("/runs/latest", status_code=status.HTTP_200_OK)
async def get_latest_sync_run(
    source_system: Optional[str] = Query(None),
    sync_repo: SyncRepository = Depends(get_sync_repository),
) -> Any:
    """Retrieve the most recent telemetry sync execution record."""
    run = await sync_repo.get_latest_sync_run(source_system=source_system)
    if not run:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": "No synchronization runs recorded."},
        )
    return run


@router.get("/runs/{run_id}", status_code=status.HTTP_200_OK)
async def get_sync_run_by_id(
    run_id: str,
    sync_repo: SyncRepository = Depends(get_sync_repository),
) -> Any:
    """Retrieve details and error diagnostic traces for a specific sync execution."""
    run = await sync_repo.get_by_id(run_id)
    if not run:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": f"Sync run with ID {run_id} not found."},
        )
    return run


@router.post("/trigger", status_code=status.HTTP_202_ACCEPTED)
async def trigger_manual_sync(
    background_tasks: BackgroundTasks,
    source_system: str = Query("ALL", description="SOLARWINDS, INTUNE, or ALL"),
    sync_service: SyncService = Depends(get_sync_service),
) -> Dict[str, Any]:
    """Manually trigger an asynchronous telemetry ingestion cycle."""
    background_tasks.add_task(sync_service.execute_sync_with_lock, source_system=source_system)
    return {
        "message": f"Telemetry synchronization for {source_system} initiated in background.",
        "status": "ACCEPTED",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
