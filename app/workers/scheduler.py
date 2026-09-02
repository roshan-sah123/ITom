"""APScheduler asynchronous periodic background worker for ITOM telemetry ingestion."""

import logging
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings
from app.core.database import AsyncSessionLocal

logger = logging.getLogger("itom.scheduler")

# Global scheduler instance
_scheduler: Optional[AsyncIOScheduler] = None

JOB_ID = "telemetry_sync_10m"
JOB_NAME = "10-Minute Multi-Domain Telemetry Ingestion"


async def run_periodic_telemetry_sync() -> None:
    """Scheduled task executing multi-domain telemetry ingestion with advisory lock protection."""
    from app.services.sync_service import SyncService

    logger.info("Executing scheduled 10-minute telemetry synchronization...")
    async with AsyncSessionLocal() as session:
        try:
            sync_service = SyncService(session)
            result = await sync_service.execute_sync_with_lock(source_system="ALL")
            logger.info("Scheduled sync completed with status: %s", result.get("status"))
        except Exception as exc:
            logger.error("Scheduled sync execution failed: %s", exc, exc_info=True)


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure AsyncIOScheduler with 10-minute interval trigger."""
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        run_periodic_telemetry_sync,
        trigger=IntervalTrigger(seconds=settings.SYNC_INTERVAL_SECONDS),
        id=JOB_ID,
        name=JOB_NAME,
        max_instances=1,
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=60,
    )
    return scheduler


def start_scheduler() -> AsyncIOScheduler:
    """Start the background async scheduler."""
    global _scheduler
    if _scheduler is None or not _scheduler.running:
        _scheduler = create_scheduler()
        _scheduler.start()
        logger.info("APScheduler async worker started (10-minute cadence / %d seconds).", settings.SYNC_INTERVAL_SECONDS)
    return _scheduler


def stop_scheduler() -> None:
    """Gracefully shut down the background scheduler."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler async worker stopped.")
        _scheduler = None


def get_scheduler() -> Optional[AsyncIOScheduler]:
    """Get active scheduler instance."""
    global _scheduler
    return _scheduler
