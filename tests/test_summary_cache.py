import asyncio

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.services import sync_service as sync_service_module
from app.services.ci_service import CIService
from app.services.summary_cache import (
    AsyncSummaryCache,
    invalidate_summaries_for_sources,
    summary_cache_key,
)
from app.services.summary_cache import summary_cache
from app.services.sync_service import SyncService
from app.services.telemetry_sources import normalize_solarwinds_node


@pytest_asyncio.fixture
async def sync_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


class _FakeSource:
    name = "SOLARWINDS"

    def __init__(self, error=None):
        self.error = error

    def fetch(self):
        if self.error:
            raise RuntimeError(self.error)
        return [normalize_solarwinds_node({"NodeID": 1, "Status": 1, "Caption": "node-1"})]


class _SummaryRepositoryStub:
    def __init__(self):
        self.calls = {"intune": 0, "solarwinds": 0}

    async def get_intune_summary(self):
        self.calls["intune"] += 1
        return {"generated_at": "intune", "metrics": {"total": 1}}

    async def get_solarwinds_summary(self):
        self.calls["solarwinds"] += 1
        return {"generated_at": "solarwinds", "metrics": {"total": 2}}


class _CIRepositoryStub:
    session = None

    def __init__(self):
        self.summary_calls = 0

    async def get_cmdb_summary(self):
        self.summary_calls += 1
        return {"generated_at": "cmdb", "total_cis": 3}


@pytest.mark.asyncio
async def test_cache_reuses_value_and_returns_independent_copies():
    cache = AsyncSummaryCache(ttl_seconds=30)
    calls = 0

    async def load():
        nonlocal calls
        calls += 1
        return {"metrics": {"total": 5}}

    first = await cache.get_or_load("solarwinds", load)
    first["metrics"]["total"] = 0
    second = await cache.get_or_load("solarwinds", load)

    assert calls == 1
    assert second == {"metrics": {"total": 5}}


@pytest.mark.asyncio
async def test_expired_cache_keeps_last_good_value_when_reload_fails(monkeypatch):
    cache = AsyncSummaryCache(ttl_seconds=1)
    now = 100.0
    monkeypatch.setattr("app.services.summary_cache.time.monotonic", lambda: now)

    async def load_good():
        return {"generated_at": "good", "metrics": {"total": 5}}

    async def load_failed():
        raise RuntimeError("temporary database failure")

    await cache.get_or_load("intune", load_good)
    now += 2

    assert await cache.get_or_load("intune", load_failed) == {
        "generated_at": "good",
        "metrics": {"total": 5},
    }


@pytest.mark.asyncio
async def test_source_sync_invalidates_only_affected_summaries_and_cmdb():
    cache = AsyncSummaryCache(ttl_seconds=30)
    calls = {"solarwinds": 0, "intune": 0, "cmdb": 0}

    def loader(key):
        async def load():
            calls[key] += 1
            return {"call": calls[key]}
        return load

    for key in calls:
        await cache.get_or_load(key, loader(key))

    # Exercise the mapping used by the shared cache invalidator.
    invalidate_summaries_for_sources({"SOLARWINDS"}, cache=cache)

    for key in calls:
        await cache.get_or_load(key, loader(key))

    assert calls == {"solarwinds": 2, "intune": 1, "cmdb": 2}


@pytest.mark.asyncio
async def test_summary_keys_are_isolated_by_database_engine():
    cache = AsyncSummaryCache(ttl_seconds=30)
    session_one = type("SessionStub", (), {"bind": object()})()
    session_two = type("SessionStub", (), {"bind": object()})()
    calls = {"one": 0, "two": 0}

    async def load_one():
        calls["one"] += 1
        return {"database": "one"}

    async def load_two():
        calls["two"] += 1
        return {"database": "two"}

    key_one = summary_cache_key(session_one, "solarwinds")
    key_two = summary_cache_key(session_two, "solarwinds")
    await cache.get_or_load(key_one, load_one)
    await cache.get_or_load(key_two, load_two)
    invalidate_summaries_for_sources({"SOLARWINDS"}, cache=cache, session=session_one)
    await cache.get_or_load(key_one, load_one)
    await cache.get_or_load(key_two, load_two)

    assert key_one != key_two
    assert calls == {"one": 2, "two": 1}


@pytest.mark.asyncio
async def test_ci_service_uses_cache_for_dashboard_summaries():
    summary_cache.invalidate()
    ci_repository = _CIRepositoryStub()
    service = CIService(ci_repository)
    summary_repository = _SummaryRepositoryStub()
    service.summary_repo = summary_repository

    first = await asyncio.gather(
        service.get_cmdb_summary(),
        service.get_intune_summary(),
        service.get_solarwinds_summary(),
    )
    second = await asyncio.gather(
        service.get_cmdb_summary(),
        service.get_intune_summary(),
        service.get_solarwinds_summary(),
    )

    assert first == second
    assert ci_repository.summary_calls == 1
    assert summary_repository.calls == {"intune": 1, "solarwinds": 1}
    summary_cache.invalidate()


@pytest.mark.asyncio
async def test_invalidation_during_load_does_not_store_pre_sync_summary():
    cache = AsyncSummaryCache(ttl_seconds=30)
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def load():
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set()
            await release.wait()
            return {"version": "before-sync"}
        return {"version": "after-sync"}

    pending = asyncio.create_task(cache.get_or_load("cmdb", load))
    await started.wait()
    cache.invalidate("cmdb")
    release.set()

    assert await pending == {"version": "after-sync"}
    assert await cache.get_or_load("cmdb", load) == {"version": "after-sync"}
    assert calls == 2


@pytest.mark.asyncio
async def test_persisted_sync_invalidates_summaries_only_after_commit(sync_session, monkeypatch):
    invalidations = []

    def capture_invalidation(sources, **kwargs):
        assert not sync_session.in_transaction()
        invalidations.append(set(sources))

    monkeypatch.setattr(sync_service_module, "invalidate_summaries_for_sources", capture_invalidation)
    monkeypatch.setattr(
        sync_service_module, "build_sources", lambda source_system, offline=False: [_FakeSource()]
    )

    result = await SyncService(sync_session).execute_sync_with_lock(source_system="SOLARWINDS")

    assert result["status"] == "SUCCESS"
    assert invalidations == [{"SOLARWINDS"}]


@pytest.mark.asyncio
async def test_failed_source_does_not_invalidate_good_summaries(sync_session, monkeypatch):
    invalidations = []
    monkeypatch.setattr(
        sync_service_module,
        "invalidate_summaries_for_sources",
        lambda sources, **kwargs: invalidations.append(set(sources)),
    )
    monkeypatch.setattr(
        sync_service_module,
        "build_sources",
        lambda source_system, offline=False: [_FakeSource(error="upstream unavailable")],
    )

    result = await SyncService(sync_session).execute_sync_with_lock(source_system="SOLARWINDS")

    assert result["status"] == "FAILED"
    assert invalidations == []
