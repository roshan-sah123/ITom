"""Regression tests for source-backed location and network inventory contracts."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.repositories.ci_repository import CIRepository
from app.services.telemetry_sources import normalize_solarwinds_node
from tests.factories import make_ci as _ci


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
async def test_location_filter_is_applied_before_pagination(session):
    """A location query must return its own correct total, not filter one page in the UI."""
    session.add_all([
        _ci("SOLARWINDS", "PUNE-01", "Up", "High", location="Pune"),
        _ci("SOLARWINDS", "PUNE-02", "Up", "High", location="Pune"),
        _ci("SOLARWINDS", "NOIDA-01", "Up", "High", location="Noida"),
        _ci("SOLARWINDS", "NO-LOCATION", "Up", "High", location=None),
    ])
    await session.flush()

    repo = CIRepository(session)
    pune_items, pune_total = await repo.get_cis_paginated(
        source_system="SOLARWINDS", location="Pune", page=1, page_size=1
    )
    unassigned_items, unassigned_total = await repo.get_cis_paginated(
        source_system="SOLARWINDS", location="Unassigned"
    )

    assert pune_total == 2
    assert len(pune_items) == 1
    assert pune_items[0].location == "Pune"
    assert unassigned_total == 1
    assert unassigned_items[0].name == "NO-LOCATION"


@pytest.mark.asyncio
async def test_network_inventory_is_source_backed_and_excludes_non_network_nodes(session):
    session.add_all([
        _ci("SOLARWINDS", "SWITCH-01", "Up", "High", ci_type="Cisco Catalyst Switch", vendor="Cisco", location="Pune"),
        _ci("SOLARWINDS", "SERVER-01", "Up", "High", ci_type="Windows Server", vendor="Dell", location="Pune"),
        _ci("INTUNE", "LAPTOP-01", "Compliant", "High", ci_type="Windows", vendor="Cisco", location="Pune"),
    ])
    await session.flush()

    items, total = await CIRepository(session).get_network_devices(location="Pune")

    assert total == 1
    assert items[0].name == "SWITCH-01"
    assert items[0].source_system == "SOLARWINDS"


@pytest.mark.asyncio
async def test_site_catalog_collapses_case_only_location_variants(session):
    """One physical site must not appear twice because source casing differs."""
    session.add_all([
        _ci("SOLARWINDS", "BLR-01", "Up", "High", location="BANGALORE"),
        _ci("SOLARWINDS", "BLR-02", "Warning", "Medium", location="Bangalore"),
        _ci("SOLARWINDS", "BLR-03", "Up", "High", location="BANGALORE"),
    ])
    await session.flush()

    sites = await CIRepository(session).get_solarwinds_sites()

    assert len(sites) == 1
    assert sites[0]["name"] == "BANGALORE"  # most-used spelling from SolarWinds
    assert sites[0]["total_nodes"] == 3
    assert sites[0]["up_nodes"] == 2
    assert sites[0]["warning_nodes"] == 1


def test_solarwinds_location_uses_itsm_property_when_city_is_empty():
    result = normalize_solarwinds_node({
        "NodeID": 1,
        "Caption": "NETWORK-01",
        "Status": 1,
        "ITSM_Location": "Bengaluru DC",
        "City": " ",
    })

    assert result is not None
    assert result["location"] == "Bengaluru DC"
    assert result["attributes"]["itsm_location"] == "Bengaluru DC"
