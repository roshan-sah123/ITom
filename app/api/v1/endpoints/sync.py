"""Telemetry synchronization management, audit history, and trigger endpoints."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from typing import Literal
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from app.api.deps import get_sync_repository, get_sync_service
from app.repositories.sync_repository import SyncRepository
from app.schemas.sync import SyncRunRead
from app.services.sync_service import SyncService
from app.workers.scheduler import get_scheduler

router = APIRouter(prefix="/sync", tags=["Telemetry Sync Engine"])


def _utc_iso(value: Optional[datetime]) -> Optional[str]:
    """Serialize SQLite-naive persisted UTC timestamps with an explicit offset."""
    if value is None:
        return None
    normalized = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return normalized.isoformat()


@router.get("/scheduler", status_code=status.HTTP_200_OK)
async def get_scheduler_status() -> Dict[str, Any]:
    """Return the scheduler state from this running API process."""
    scheduler = get_scheduler()
    job = scheduler.get_job("telemetry_sync_10m") if scheduler and scheduler.running else None
    next_run = job.next_run_time if job else None
    return {
        "enabled": settings.SCHEDULER_ENABLED,
        "running": bool(scheduler and scheduler.running),
        "interval_seconds": settings.SYNC_INTERVAL_SECONDS,
        "next_run": _utc_iso(next_run),
        "timezone": next_run.tzname() if next_run else str(scheduler.timezone) if scheduler else "Unavailable",
    }


@router.get("/status", status_code=status.HTTP_200_OK)
async def get_sync_status(
    sync_repo: SyncRepository = Depends(get_sync_repository),
) -> Dict[str, Any]:
    """Retrieve the current telemetry sync status, freshness, and last execution details."""
    latest_sw = await sync_repo.get_latest_sync_run(source_system="SOLARWINDS")
    latest_intune = await sync_repo.get_latest_sync_run(source_system="INTUNE")
    now = datetime.now(timezone.utc)

    completed_runs = [r for r in (latest_sw, latest_intune) if r and r.completed_at]
    last_run = max(completed_runs, key=lambda r: r.completed_at.replace(tzinfo=timezone.utc)) if completed_runs else None
    last_sync_time = last_run.completed_at if last_run and last_run.completed_at else None

    age_seconds = None
    sync_state = "IDLE"
    state_reason = "No synchronization runs recorded yet."
    failed_sources = []
    healthy_sources = []
    if last_sync_time:
        if last_sync_time.tzinfo is None:
            last_sync_time = last_sync_time.replace(tzinfo=timezone.utc)
        age_seconds = max(0, int((now - last_sync_time).total_seconds()))
        _tracked = {"SOLARWINDS": latest_sw, "INTUNE": latest_intune}
        _seen = {n: r for n, r in _tracked.items() if r is not None}
        failed_sources = sorted(n for n, r in _seen.items() if r.status == "FAILED")
        healthy_sources = sorted(n for n, r in _seen.items() if r.status == "SUCCESS")

        if failed_sources and not healthy_sources:
            sync_state = "FAILED"
            state_reason = f"All tracked sources failed: {', '.join(failed_sources)}."
        elif failed_sources:
            sync_state = "DEGRADED"
            state_reason = f"Partial failure - {', '.join(failed_sources)} failed."
        elif len(healthy_sources) != 2:
            sync_state = "DEGRADED"
            state_reason = "Both source successes have not been confirmed."
        elif any((now - r.completed_at.replace(tzinfo=timezone.utc)).total_seconds() > max(900, settings.SYNC_INTERVAL_SECONDS * 2.5) for r in completed_runs):
            sync_state = "DEGRADED"
            state_reason = f"Sources succeeded, but data is {age_seconds}s old."
        else:
            sync_state = "HEALTHY"
            state_reason = "All tracked sources synchronized successfully and recently."

    return {
        "sync_state": sync_state,
        "state_reason": state_reason,
        "healthy_sources": healthy_sources,
        "failed_sources": failed_sources,
        "cadence_seconds": settings.SYNC_INTERVAL_SECONDS,
        "age_seconds": age_seconds,
        "last_sync": _utc_iso(last_sync_time),
        "solarwinds": {
            "status": latest_sw.status if latest_sw else "UNKNOWN",
            "last_completed": _utc_iso(latest_sw.completed_at if latest_sw else None),
            "duration_ms": latest_sw.duration_ms if latest_sw else None,
            "records_processed": latest_sw.records_processed if latest_sw else 0,
        },
        "intune": {
            "status": latest_intune.status if latest_intune else "UNKNOWN",
            "last_completed": _utc_iso(latest_intune.completed_at if latest_intune else None),
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
    source_system: Literal["ALL", "SOLARWINDS", "INTUNE"] = Query("ALL"),
) -> Dict[str, Any]:
    """Manually trigger an asynchronous telemetry ingestion cycle."""
    background_tasks.add_task(run_manual_sync, source_system)
    return {
        "message": f"Telemetry synchronization for {source_system} initiated in background.",
        "status": "ACCEPTED",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def run_manual_sync(source_system):
    """A background task owns its session beyond the request lifetime."""
    async with AsyncSessionLocal() as session:
        await SyncService(session).execute_sync_with_lock(source_system=source_system)
