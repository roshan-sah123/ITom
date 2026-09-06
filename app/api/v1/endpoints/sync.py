"""Telemetry synchronization management, audit history, and trigger endpoints."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from app.api.deps import get_sync_repository, get_sync_service
from app.repositories.sync_repository import SyncRepository
from app.schemas.sync import SyncRunRead
from app.services.sync_service import SyncService

router = APIRouter(prefix="/sync", tags=["Telemetry Sync Engine"])


@router.get("/status", status_code=status.HTTP_200_OK)
async def get_sync_status(
    sync_repo: SyncRepository = Depends(get_sync_repository),
) -> Dict[str, Any]:
    """Retrieve the current telemetry sync status, freshness, and last execution details."""
    latest_sw = await sync_repo.get_latest_sync_run(source_system="SOLARWINDS")
    latest_intune = await sync_repo.get_latest_sync_run(source_system="INTUNE")
    now = datetime.now(timezone.utc)

    last_run = latest_sw or latest_intune
    last_sync_time = last_run.completed_at if last_run and last_run.completed_at else None

    age_seconds = None
    sync_state = "IDLE"
    if last_sync_time:
        if last_sync_time.tzinfo is None:
            last_sync_time = last_sync_time.replace(tzinfo=timezone.utc)
        age_seconds = max(0, int((now - last_sync_time).total_seconds()))
        sync_state = "HEALTHY" if age_seconds <= 900 else "DEGRADED"

    return {
        "sync_state": sync_state,
        "cadence_seconds": 600,
        "age_seconds": age_seconds,
        "last_sync": last_sync_time.isoformat() if last_sync_time else None,
        "solarwinds": {
            "status": latest_sw.status if latest_sw else "UNKNOWN",
            "last_completed": latest_sw.completed_at.isoformat() if latest_sw and latest_sw.completed_at else None,
            "duration_ms": latest_sw.duration_ms if latest_sw else None,
            "records_processed": latest_sw.records_processed if latest_sw else 0,
        },
        "intune": {
            "status": latest_intune.status if latest_intune else "UNKNOWN",
            "last_completed": latest_intune.completed_at.isoformat() if latest_intune and latest_intune.completed_at else None,
            "duration_ms": latest_intune.duration_ms if latest_intune else None,
            "records_processed": latest_intune.records_processed if latest_intune else 0,
        },
        "timestamp": now.isoformat(),
    }


@router.get("/runs", status_code=status.HTTP_200_OK)
async def list_sync_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sync_repo: SyncRepository = Depends(get_sync_repository),
) -> List[Any]:
    """Retrieve audit history of background telemetry synchronization runs."""
    runs = await sync_repo.get_sync_runs_paginated(page=page, page_size=page_size)
    return [
        SyncRunRead.model_validate(r).model_dump(mode="json")
        if hasattr(r, "__table__")
        else (r.to_dict() if hasattr(r, "to_dict") else r)
        for r in runs
    ]


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
    if hasattr(run, "__table__"):
        return SyncRunRead.model_validate(run).model_dump(mode="json")
    if hasattr(run, "to_dict"):
        return run.to_dict()
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
    if hasattr(run, "__table__"):
        return SyncRunRead.model_validate(run).model_dump(mode="json")
    if hasattr(run, "to_dict"):
        return run.to_dict()
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
