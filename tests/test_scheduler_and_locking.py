"""Current scheduler settings and production sync-lock code paths."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.sync import SyncRun
from app.services.sync_service import SyncService
from app.workers.scheduler import create_scheduler, JOB_ID


def test_scheduler_uses_configured_interval_and_no_overlapping_jobs(monkeypatch):
    monkeypatch.setattr(settings, "SYNC_INTERVAL_SECONDS", 17)
    job = create_scheduler().get_job(JOB_ID)
    assert job.trigger.interval.total_seconds() == 17
    assert job.max_instances == 1 and job.coalesce is True


async def test_postgres_lock_is_transaction_scoped():
    db = AsyncMock()
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    db.execute.return_value = Mock(scalar=Mock(return_value=True))
    assert await SyncService(db)._acquire_lock() is True
    statement, params = db.execute.call_args.args
    assert str(statement) == "SELECT pg_try_advisory_xact_lock(:key)"
    assert params == {"key": settings.ADVISORY_LOCK_ID}


async def test_postgres_lock_failure_is_not_bypassed():
    db = AsyncMock()
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    db.execute.side_effect = OSError("connection lost")
    with pytest.raises(RuntimeError, match="sync lock unavailable"):
        await SyncService(db)._acquire_lock()


async def test_sqlite_overlap_skips_source_fetch_and_error_releases_lock(session, db_session_factory, monkeypatch):
    from app.services import sync_service
    monkeypatch.setattr(sync_service, "_in_memory_locked", False)
    owner = SyncService(session)
    assert await owner._acquire_lock() is True
    async with db_session_factory() as peer_db:
        peer = SyncService(peer_db)
        fetch = AsyncMock()
        monkeypatch.setattr(peer, "_fetch_source", fetch)
        assert (await peer.execute_sync_with_lock(source_system="INTUNE"))["status"] == "SKIPPED"
        fetch.assert_not_awaited()
    owner._release_in_memory_lock()
    failed = await owner.execute_sync_with_lock(source_system="INTUNE", should_fail=True)
    assert failed["status"] == "FAILED"
    assert (await session.execute(select(SyncRun))).scalars().one().status == "FAILED"
    assert await owner._acquire_lock() is True
    owner._release_in_memory_lock()
