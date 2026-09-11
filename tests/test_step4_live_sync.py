"""STEP 4 VERIFICATION - live ingestion must be real, and must be able to fail.

What these tests prove
----------------------
1. Every Orion status survives the mapping. Critical and Unmanaged must NOT
   collapse into "Down", and health_tier "Low" must be reachable.
2. A source that raises is recorded as FAILED - the freshness clock must not
   advance on a broken extraction. Under the old file-reading design a sync
   literally could not fail.
3. Each source gets its own SyncRun, so one domain succeeding cannot make a
   failed domain look fresh.
4. Delta detection ignores CPU/RAM churn and only writes history on a real
   state transition.
5. Intune devices are actually ingested (the old code had no Intune branch).

Run:
    python -m pytest tests/test_step4_live_sync.py -v
"""

import uuid
from typing import Any, Dict, List

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.ci import ConfigurationItem
from app.models.history import CIStatusHistory
from app.models.sync import SyncRun
from app.services.sync_service import SyncService
from app.services.telemetry_sources import (
    ORION_STATUS_MAP,
    SourceUnavailableError,
    normalize_intune_device,
    normalize_solarwinds_node,
    normalize_vendor,
)


class FakeSource:
    """A telemetry source returning a fixed payload, or raising on demand."""

    def __init__(self, name: str, items: List[Dict[str, Any]] = None, error: str = None):
        self.name = name
        self._items = items or []
        self._error = error
        self.fetch_count = 0

    def fetch(self) -> List[Dict[str, Any]]:
        self.fetch_count += 1
        if self._error:
            raise SourceUnavailableError(self._error)
        return self._items


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


# --------------------------------------------------------------------------- #
# 1. Orion status mapping - the bug that turned 6 Down into 153
# --------------------------------------------------------------------------- #

def test_every_orion_status_maps_distinctly():
    cases = {
        1: ("Up", "High"),
        2: ("Down", "Low"),
        3: ("Warning", "Medium"),
        4: ("Shutdown", "Medium"),
        9: ("Unmanaged", "Medium"),
        14: ("Critical", "Low"),
    }
    for code, (expected_status, expected_health) in cases.items():
        item = normalize_solarwinds_node({"NodeID": code, "Status": code, "Caption": f"N{code}"})
        assert item["status"] == expected_status, f"Status {code} mis-mapped"
        assert item["health_tier"] == expected_health, f"Health for {code} mis-mapped"

    # The critical regression: these must never be reported as Down.
    assert normalize_solarwinds_node({"NodeID": 1, "Status": 14})["status"] == "Critical"
    assert normalize_solarwinds_node({"NodeID": 2, "Status": 9})["status"] == "Unmanaged"


def test_low_health_tier_is_reachable():
    """The old mapping only emitted High/Medium, making 'Low' unreachable."""
    down = normalize_solarwinds_node({"NodeID": 1, "Status": 2})
    assert down["health_tier"] == "Low"

    # Resource pressure also downgrades an otherwise-Up node.
    hot = normalize_solarwinds_node({"NodeID": 2, "Status": 1, "CPULoad": 96.0})
    assert hot["health_tier"] == "Low"


def test_resource_pressure_downgrades_to_medium():
    warm = normalize_solarwinds_node({"NodeID": 3, "Status": 1, "CPULoad": 80.0})
    assert warm["health_tier"] == "Medium"


def test_microsoft_devices_are_not_bucketed_as_other():
    """include_microsoft defaulted to False, so every Surface became 'Other'."""
    assert normalize_vendor("Microsoft Corporation") == "Microsoft"
    assert normalize_vendor("Dell Inc.") == "Dell"
    assert normalize_vendor("Hewlett-Packard") == "HP"
    assert normalize_vendor("LENOVO") == "Lenovo"
    assert normalize_vendor(None) == "Other"


# --------------------------------------------------------------------------- #
# 2. Intune normalisation - the branch that never existed
# --------------------------------------------------------------------------- #

def test_intune_device_normalisation_matches_seed_shape():
    item = normalize_intune_device({
        "id": "abc-123",
        "deviceName": "LAP-0042",
        "operatingSystem": "Windows",
        "osVersion": "10.0.19045",
        "complianceState": "compliant",
        "manufacturer": "Dell Inc.",
        "totalStorageSpaceInBytes": 512_000_000_000,
        "freeStorageSpaceInBytes": 256_000_000_000,
    })
    assert item["external_id"] == "abc-123"
    assert item["status"] == "Compliant"
    assert item["health_tier"] == "High"
    assert item["ci_type"] == "Windows"
    assert item["vendor"] == "Dell"
    assert item["attributes"]["total_storage_bytes"] == 512_000_000_000


def test_intune_noncompliant_maps_to_low_health():
    item = normalize_intune_device({"id": "x", "complianceState": "noncompliant"})
    assert item["status"] == "Noncompliant"
    assert item["health_tier"] == "Low"


def test_device_without_id_is_skipped():
    assert normalize_intune_device({"deviceName": "ghost"}) is None


# --------------------------------------------------------------------------- #
# 3. Failures must be recorded as FAILED
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_unreachable_source_is_recorded_as_failed(session: AsyncSession):
    service = SyncService(session)
    broken = FakeSource("INTUNE", error="401 Unauthorized from Microsoft Graph")

    result = await service.sync_single_source(broken)

    assert result["status"] == "FAILED"
    assert "401" in result["error"]
    assert result["items_extracted"] == 0

    runs = (await session.execute(select(SyncRun))).scalars().all()
    assert len(runs) == 1
    assert runs[0].status == "FAILED"
    assert runs[0].source_system == "INTUNE"


@pytest.mark.asyncio
async def test_empty_extraction_is_a_failure_not_a_success(session: AsyncSession):
    """Zero records means a broken extraction, not an empty fleet."""
    service = SyncService(session)
    result = await service.sync_single_source(FakeSource("SOLARWINDS", items=[]))

    assert result["status"] == "FAILED"
    runs = (await session.execute(select(SyncRun))).scalars().all()
    assert runs[0].status == "FAILED"


# --------------------------------------------------------------------------- #
# 4. Per-source audit isolation
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_each_source_gets_its_own_sync_run(session: AsyncSession):
    service = SyncService(session)

    good = [normalize_solarwinds_node({"NodeID": 1, "Status": 1, "Caption": "SRV-1"})]
    await service.sync_single_source(FakeSource("SOLARWINDS", items=good))
    await service.sync_single_source(FakeSource("INTUNE", error="Graph unreachable"))

    runs = (await session.execute(select(SyncRun))).scalars().all()
    by_source = {r.source_system: r.status for r in runs}

    assert by_source["SOLARWINDS"] == "SUCCESS"
    assert by_source["INTUNE"] == "FAILED"
    # A SolarWinds success must never mask the Intune failure.
    assert len(runs) == 2


# --------------------------------------------------------------------------- #
# 5. Delta detection writes history only on real change
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_cpu_churn_does_not_write_history(session: AsyncSession):
    """The old fingerprint included CPU/RAM, writing ~223k rows per day."""
    service = SyncService(session)

    first = [normalize_solarwinds_node({"NodeID": 7, "Status": 1, "Caption": "SRV-7", "CPULoad": 10.0})]
    await service.sync_single_source(FakeSource("SOLARWINDS", items=first))

    history_after_first = len((await session.execute(select(CIStatusHistory))).scalars().all())
    assert history_after_first == 1  # initial ingestion

    # Same state, different CPU load - must NOT write a history row.
    second = [normalize_solarwinds_node({"NodeID": 7, "Status": 1, "Caption": "SRV-7", "CPULoad": 42.0})]
    result = await service.sync_single_source(FakeSource("SOLARWINDS", items=second))

    assert result["items_unchanged"] == 1
    assert result["items_updated"] == 0
    history_after_second = len((await session.execute(select(CIStatusHistory))).scalars().all())
    assert history_after_second == 1, "CPU churn must not create history rows"


@pytest.mark.asyncio
async def test_real_state_transition_does_write_history(session: AsyncSession):
    service = SyncService(session)

    up = [normalize_solarwinds_node({"NodeID": 9, "Status": 1, "Caption": "SRV-9"})]
    await service.sync_single_source(FakeSource("SOLARWINDS", items=up))

    down = [normalize_solarwinds_node({"NodeID": 9, "Status": 2, "Caption": "SRV-9"})]
    result = await service.sync_single_source(FakeSource("SOLARWINDS", items=down))

    assert result["items_updated"] == 1
    rows = (await session.execute(select(CIStatusHistory))).scalars().all()
    assert len(rows) == 2

    latest = sorted(rows, key=lambda r: r.recorded_at)[-1]
    assert latest.previous_status == "Up"
    assert latest.status == "Down"

    ci = (await session.execute(select(ConfigurationItem))).scalars().first()
    assert ci.status == "Down"
    assert ci.health_tier == "Low"


@pytest.mark.asyncio
async def test_attributes_merge_persists(session: AsyncSession):
    """In-place dict mutation was silently discarded by SQLAlchemy."""
    service = SyncService(session)

    await service.sync_single_source(FakeSource("SOLARWINDS", items=[
        normalize_solarwinds_node({"NodeID": 11, "Status": 1, "Caption": "SRV-11", "City": "Mumbai"})
    ]))
    await service.sync_single_source(FakeSource("SOLARWINDS", items=[
        normalize_solarwinds_node({"NodeID": 11, "Status": 2, "Caption": "SRV-11", "Contact": "NOC"})
    ]))

    ci = (await session.execute(select(ConfigurationItem))).scalars().first()
    assert ci.attributes.get("contact") == "NOC"
    assert ci.attributes.get("orion_status_code") == 2
