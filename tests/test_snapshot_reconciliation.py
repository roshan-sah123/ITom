import pytest
from sqlalchemy import select, func
from app.models.ci import ConfigurationItem
from app.repositories.summary_repository import SummaryRepository
from app.repositories.ci_repository import CIRepository
from app.services.sync_service import SyncService
from app.services.telemetry_sources import SolarWindsSource, SourceUnavailableError, validated_snapshot, normalize_solarwinds_node


class Client:
    def __init__(self, rows):
        self.rows = rows

    def fetch_nodes(self):
        return self.rows


def rows(*ids):
    return [dict(NodeID=i, Caption=f"test-{i}", Status=1, City="Test Site") for i in ids]


@pytest.mark.asyncio
async def test_complete_snapshot_retirement_and_reappearance(session):
    service = SyncService(session)
    first = await service.sync_single_source(SolarWindsSource(Client(rows(1, 2))))
    await session.commit()
    assert first["items_persisted"] == 2
    second = await service.sync_single_source(SolarWindsSource(Client(rows(1))))
    await session.commit()
    assert second["items_retired"] == 1
    assert await session.scalar(select(func.count()).select_from(ConfigurationItem)) == 1
    assert await session.scalar(select(func.count()).select_from(ConfigurationItem).execution_options(include_retired=True)) == 2
    assert (await SummaryRepository(session).get_solarwinds_summary())["metrics"]["total_cis"] == 1
    assert (await CIRepository(session).get_cis_paginated())[1] == 1
    third = await service.sync_single_source(SolarWindsSource(Client(rows(1, 2))))
    await session.commit()
    assert third["items_persisted"] == 0
    assert await session.scalar(select(func.count()).select_from(ConfigurationItem)) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_rows", [[], rows(1, 1), [{"Caption": "missing ID"}], ["malformed"]])
async def test_invalid_snapshot_cannot_retire(session, bad_rows):
    service = SyncService(session)
    await service.sync_single_source(SolarWindsSource(Client(rows(1, 2))))
    await session.commit()
    result = await service.sync_single_source(SolarWindsSource(Client(bad_rows)))
    await session.commit()
    assert result["status"] == "FAILED"
    assert await session.scalar(select(func.count()).select_from(ConfigurationItem)) == 2


@pytest.mark.asyncio
async def test_stable_status_updates_location_and_attributes(session):
    service = SyncService(session)
    await service.sync_single_source(SolarWindsSource(Client(rows(1))))
    await session.commit()
    changed = rows(1)
    changed[0]["City"] = "New Site"
    changed[0]["CPULoad"] = 12
    result = await service.sync_single_source(SolarWindsSource(Client(changed)))
    await session.commit()
    item = (await session.execute(select(ConfigurationItem))).scalar_one()
    assert item.location == "New Site"
    assert item.attributes["cpu_load"] == 12
    assert result["items_updated"] == 1


@pytest.mark.asyncio
async def test_transaction_failure_rolls_back_inventory(session, monkeypatch):
    service = SyncService(session)
    await service.sync_single_source(SolarWindsSource(Client(rows(1, 2))))
    await session.commit()
    async def fail_after_retirement(*args):
        await SyncService.retire_missing(service, *args)
        raise RuntimeError("Injected transaction failure")
    monkeypatch.setattr(service, "retire_missing", fail_after_retirement)
    result = await service.sync_single_source(SolarWindsSource(Client(rows(1))))
    await session.commit()
    assert result["status"] == "FAILED"
    assert await session.scalar(select(func.count()).select_from(ConfigurationItem)) == 2
