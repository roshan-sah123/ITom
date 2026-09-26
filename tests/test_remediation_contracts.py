"""Tests verifying the remediation of findings from the ITOM operational audit."""

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.ci import ConfigurationItem
from app.repositories.ci_repository import CIRepository
from app.repositories.summary_repository import SummaryRepository


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as db_session:
        yield db_session
    await engine.dispose()


@pytest.mark.asyncio
async def test_saturation_telemetry_returns_saturated_nodes(session):
    now = datetime.now(timezone.utc)
    # Add nodes: 1 high CPU, 1 high RAM, 1 healthy, 1 retired
    session.add_all([
        ConfigurationItem(
            source_id="SW-1", source_system="SOLARWINDS", name="SAT-CPU-NODE",
            ci_type="Server", status="Up", health_tier="Medium", vendor="Dell",
            last_sync_time=now, is_active=True,
            attributes={"cpu_load": 85.0, "memory_used": 50.0},
        ),
        ConfigurationItem(
            source_id="SW-2", source_system="SOLARWINDS", name="SAT-RAM-NODE",
            ci_type="Cisco C9200L", status="Warning", health_tier="Medium", vendor="Cisco",
            last_sync_time=now, is_active=True,
            attributes={"cpu_load": 30.0, "memory_used": 92.0},
        ),
        ConfigurationItem(
            source_id="SW-3", source_system="SOLARWINDS", name="HEALTHY-NODE",
            ci_type="Server", status="Up", health_tier="High", vendor="Dell",
            last_sync_time=now, is_active=True,
            attributes={"cpu_load": 20.0, "memory_used": 40.0},
        ),
        ConfigurationItem(
            source_id="SW-4", source_system="SOLARWINDS", name="RETIRED-SAT-NODE",
            ci_type="Server", status="Down", health_tier="Low", vendor="Dell",
            last_sync_time=now, is_active=False,
            attributes={"cpu_load": 99.0, "memory_used": 99.0},
        ),
    ])
    await session.flush()

    repo = SummaryRepository(session)
    summary = await repo.get_solarwinds_summary()

    assert "top_saturated_servers" in summary
    sat = summary["top_saturated_servers"]
    assert len(sat) == 1
    names = [s["name"] for s in sat]
    assert "SAT-CPU-NODE" in names
    assert "SAT-RAM-NODE" not in names  # Saturated network gear is not a server triage item.
    assert "HEALTHY-NODE" not in names
    assert "RETIRED-SAT-NODE" not in names
    assert summary["total_saturated_nodes"] == 1


@pytest.mark.asyncio
async def test_classification_model_reconciliation(session):
    now = datetime.now(timezone.utc)
    session.add_all([
        # 2 Network Devices
        ConfigurationItem(
            source_id="SW-NET1", source_system="SOLARWINDS", name="SWITCH-01",
            ci_type="Cisco C9200L", status="Up", health_tier="High", vendor="Cisco",
            last_sync_time=now, is_active=True, attributes={},
        ),
        ConfigurationItem(
            source_id="SW-NET2", source_system="SOLARWINDS", name="FIREWALL-01",
            ci_type="PA-3220", status="Up", health_tier="High", vendor="Palo Alto",
            last_sync_time=now, is_active=True, attributes={},
        ),
        # 1 Server
        ConfigurationItem(
            source_id="SW-SRV1", source_system="SOLARWINDS", name="WIN-SRV-01",
            ci_type="Windows 2019 Server", status="Up", health_tier="High", vendor="Dell",
            last_sync_time=now, is_active=True, attributes={},
        ),
        # 1 Unclassified
        ConfigurationItem(
            source_id="SW-UNCL1", source_system="SOLARWINDS", name="UNKNOWN-GEAR-01",
            ci_type="Unknown", status="Up", health_tier="High", vendor="Other",
            last_sync_time=now, is_active=True, attributes={},
        ),
        # 2 Intune Endpoints
        ConfigurationItem(
            source_id="INT-1", source_system="INTUNE", name="LAPTOP-01",
            ci_type="Windows", status="Compliant", health_tier="High", vendor="Lenovo",
            last_sync_time=now, is_active=True, attributes={},
        ),
        ConfigurationItem(
            source_id="INT-2", source_system="INTUNE", name="PHONE-01",
            ci_type="iOS", status="Compliant", health_tier="High", vendor="Apple",
            last_sync_time=now, is_active=True, attributes={},
        ),
    ])
    await session.flush()

    cmdb_repo = CIRepository(session)
    cmdb_summary = await cmdb_repo.get_cmdb_summary()

    assert cmdb_summary["total_cis"] == 6
    assert cmdb_summary["total_endpoints"] == 2
    assert cmdb_summary["total_network_devices"] == 2
    assert cmdb_summary["total_servers"] == 1
    assert cmdb_summary["total_unclassified"] == 1

    # Verify get_network_devices returns the exact same 2 network devices
    _, net_total = await cmdb_repo.get_network_devices()
    assert net_total == 2


@pytest.mark.asyncio
async def test_location_analytics_normalizes_case_and_reports_scope(session):
    now = datetime.now(timezone.utc)
    session.add_all([
        ConfigurationItem(
            source_id="SW-L1", source_system="SOLARWINDS", name="NODE-BLR-1",
            ci_type="Server", status="Up", health_tier="High", vendor="Dell",
            location="BANGALORE", last_sync_time=now, is_active=True, attributes={},
        ),
        ConfigurationItem(
            source_id="SW-L2", source_system="SOLARWINDS", name="NODE-BLR-2",
            ci_type="Server", status="Up", health_tier="High", vendor="Dell",
            location="Bangalore", last_sync_time=now, is_active=True, attributes={},
        ),
        ConfigurationItem(
            source_id="SW-L3", source_system="SOLARWINDS", name="NODE-UNLOC",
            ci_type="Server", status="Up", health_tier="High", vendor="Dell",
            location="", last_sync_time=now, is_active=True, attributes={},
        ),
    ])
    await session.flush()

    summary_repo = SummaryRepository(session)
    loc_report = await summary_repo.get_location_analytics(source_system="SOLARWINDS")

    # Should collapse "BANGALORE" and "Bangalore" into 1 location
    assert loc_report["total_locations"] == 1
    assert loc_report["located_cis"] == 2
    assert loc_report["unlocated_cis"] == 1
    assert loc_report["location_scope"] == "SOLARWINDS_INFRASTRUCTURE"
    assert loc_report["location_coverage_pct"] == 66.67
