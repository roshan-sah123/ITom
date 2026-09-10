"""STEP 3 VERIFICATION - the freshness signal must be honest.

What these tests prove
----------------------
1. A never-synced system reports UNKNOWN, not a confident FRESH.
   (The old module-global reported FRESH from the moment the process booted.)
2. Recent successful syncs report FRESH; old ones report STALE.
3. Failed sync runs never advance the freshness clock.
4. Per-source reporting is independent - SolarWinds succeeding must not make
   Intune look fresh.
5. The overall status is the worst status across sources.

Run:
    python -m pytest tests/test_step3_freshness.py -v
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import ci as _ci_models  # noqa: F401  (registers tables)
from app.models import history as _history_models  # noqa: F401  (registers tables)
from app.models.base import Base
from app.models.sync import SyncRun
from app.repositories.freshness_repository import (
    STATUS_FRESH,
    STATUS_STALE,
    STATUS_UNKNOWN,
    FreshnessRepository,
    classify,
)

WINDOW = 900


def _run(source_system: str, status: str, minutes_ago: float) -> SyncRun:
    """Build a SyncRun that completed ``minutes_ago`` minutes in the past."""
    completed = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return SyncRun(
        id=uuid.uuid4(),
        source_system=source_system,
        status=status,
        records_processed=100,
        records_updated=0,
        records_unchanged=100,
        items_extracted=100,
        items_persisted=100,
        duration_ms=1200,
        started_at=completed - timedelta(seconds=2),
        completed_at=completed,
    )


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    """Isolated in-memory SQLite session with the full schema created."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s

    await engine.dispose()


# --------------------------------------------------------------------------- #
# 1. Never synced must be UNKNOWN, never FRESH
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_never_synced_reports_unknown_not_fresh(session: AsyncSession):
    report = await FreshnessRepository(session, WINDOW).get_freshness()

    assert report["overall_status"] == STATUS_UNKNOWN
    assert report["oldest_age_seconds"] is None
    for source in ("INTUNE", "SOLARWINDS"):
        assert report["sources"][source]["status"] == STATUS_UNKNOWN
        assert report["sources"][source]["last_synchronized_at"] is None


def test_classify_treats_missing_timestamp_as_unknown():
    verdict = classify(None, freshness_window_seconds=WINDOW)
    assert verdict["status"] == STATUS_UNKNOWN
    assert verdict["age_seconds"] is None


# --------------------------------------------------------------------------- #
# 2. Recent = FRESH, old = STALE
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_recent_success_is_fresh(session: AsyncSession):
    session.add_all([
        _run("INTUNE", "SUCCESS", minutes_ago=2),
        _run("SOLARWINDS", "SUCCESS", minutes_ago=3),
    ])
    await session.flush()

    report = await FreshnessRepository(session, WINDOW).get_freshness()

    assert report["overall_status"] == STATUS_FRESH
    assert report["sources"]["INTUNE"]["status"] == STATUS_FRESH
    assert report["sources"]["SOLARWINDS"]["status"] == STATUS_FRESH
    assert report["oldest_age_seconds"] < WINDOW


@pytest.mark.asyncio
async def test_old_success_is_stale(session: AsyncSession):
    session.add_all([
        _run("INTUNE", "SUCCESS", minutes_ago=180),
        _run("SOLARWINDS", "SUCCESS", minutes_ago=240),
    ])
    await session.flush()

    report = await FreshnessRepository(session, WINDOW).get_freshness()

    assert report["overall_status"] == STATUS_STALE
    assert report["sources"]["INTUNE"]["status"] == STATUS_STALE
    assert report["oldest_age_seconds"] > WINDOW


# --------------------------------------------------------------------------- #
# 3. Failures must not advance the clock
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_failed_runs_do_not_count_as_fresh(session: AsyncSession):
    session.add_all([
        _run("INTUNE", "SUCCESS", minutes_ago=300),   # last good sync: 5h ago
        _run("INTUNE", "FAILED", minutes_ago=1),      # recent, but failed
        _run("SOLARWINDS", "SUCCESS", minutes_ago=2),
    ])
    await session.flush()

    report = await FreshnessRepository(session, WINDOW).get_freshness()

    # The recent FAILED run must not make Intune look fresh.
    assert report["sources"]["INTUNE"]["status"] == STATUS_STALE
    assert report["sources"]["INTUNE"]["age_seconds"] > WINDOW
    assert report["overall_status"] == STATUS_STALE


# --------------------------------------------------------------------------- #
# 4. Sources are independent
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_one_fresh_source_does_not_mask_a_stale_one(session: AsyncSession):
    session.add_all([
        _run("SOLARWINDS", "SUCCESS", minutes_ago=1),    # fresh
        _run("INTUNE", "SUCCESS", minutes_ago=600),      # 10h old
    ])
    await session.flush()

    report = await FreshnessRepository(session, WINDOW).get_freshness()

    assert report["sources"]["SOLARWINDS"]["status"] == STATUS_FRESH
    assert report["sources"]["INTUNE"]["status"] == STATUS_STALE
    # Overall must reflect the WORST source, not the best.
    assert report["overall_status"] == STATUS_STALE


@pytest.mark.asyncio
async def test_unknown_source_outranks_stale_in_overall(session: AsyncSession):
    session.add_all([_run("SOLARWINDS", "SUCCESS", minutes_ago=600)])
    await session.flush()

    report = await FreshnessRepository(session, WINDOW).get_freshness()

    assert report["sources"]["SOLARWINDS"]["status"] == STATUS_STALE
    assert report["sources"]["INTUNE"]["status"] == STATUS_UNKNOWN
    assert report["overall_status"] == STATUS_UNKNOWN


# --------------------------------------------------------------------------- #
# 5. An ALL-domain run refreshes every source
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_all_domain_run_counts_for_every_source(session: AsyncSession):
    session.add_all([_run("ALL", "SUCCESS", minutes_ago=2)])
    await session.flush()

    report = await FreshnessRepository(session, WINDOW).get_freshness()

    assert report["overall_status"] == STATUS_FRESH
    assert report["sources"]["INTUNE"]["status"] == STATUS_FRESH
    assert report["sources"]["SOLARWINDS"]["status"] == STATUS_FRESH


@pytest.mark.asyncio
async def test_newest_success_wins_when_several_exist(session: AsyncSession):
    session.add_all([
        _run("INTUNE", "SUCCESS", minutes_ago=500),
        _run("INTUNE", "SUCCESS", minutes_ago=3),
        _run("INTUNE", "SUCCESS", minutes_ago=90),
        _run("SOLARWINDS", "SUCCESS", minutes_ago=4),
    ])
    await session.flush()

    report = await FreshnessRepository(session, WINDOW).get_freshness()

    assert report["sources"]["INTUNE"]["status"] == STATUS_FRESH
    assert report["sources"]["INTUNE"]["age_seconds"] < 600
