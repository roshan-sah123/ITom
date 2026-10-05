from datetime import datetime, timedelta, timezone
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models import sync as _sync_models  # noqa: F401
from app.models.sync import SyncRun
from app.repositories.summary_repository import SummaryRepository


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as db:
        yield db
    await engine.dispose()


@pytest.mark.asyncio
async def test_intune_forecast_projects_from_latest_successful_run_each_day(session):
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    for days_ago in range(7, -1, -1):
        completed = today - timedelta(days=days_ago) + timedelta(hours=12)
        session.add(SyncRun(
            id=uuid.uuid4(), source_system="INTUNE", status="SUCCESS",
            records_processed=1000 + (7 - days_ago) * 10,
            started_at=completed - timedelta(minutes=1), completed_at=completed,
        ))
        # A later failed retry that day must not replace the successful count.
        session.add(SyncRun(
            id=uuid.uuid4(), source_system="INTUNE", status="FAILED",
            records_processed=1, started_at=completed + timedelta(minutes=1),
            completed_at=completed + timedelta(minutes=2),
        ))
    await session.commit()

    result = await SummaryRepository(session).get_intune_device_count_forecast()

    assert result["forecast_available"] is True
    assert result["current_count"] == 1070
    assert result["forecast_count"] == 1140
    assert result["trend_per_day"] == 10.0
    assert result["observed_days"] == 8


@pytest.mark.asyncio
async def test_intune_forecast_waits_for_seven_daily_observations(session):
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    for days_ago in range(5, -1, -1):
        completed = today - timedelta(days=days_ago) + timedelta(hours=12)
        session.add(SyncRun(
            id=uuid.uuid4(), source_system="INTUNE", status="SUCCESS",
            records_processed=1000, started_at=completed - timedelta(minutes=1),
            completed_at=completed,
        ))
    await session.commit()

    result = await SummaryRepository(session).get_intune_device_count_forecast()

    assert result["forecast_available"] is False
    assert result["observed_days"] == 6
