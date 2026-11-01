"""Decision metrics distinguish observed state, missing evidence, and populations."""
from datetime import datetime, timedelta, timezone

import pytest

from app.models.ci import ConfigurationItem
from app.repositories.summary_repository import SummaryRepository


@pytest.mark.parametrize('raw,expected,tier', [
    (150, None, 'High'), (float('inf'), None, 'High'), (float('nan'), None, 'High'),
    (True, None, 'High'), (-1, None, 'High'), ('85', 85, 'Medium'), (0, 0, 'High'),
])
def test_ingested_resource_percentages_follow_decision_validation(raw, expected, tier):
    from app.services.telemetry_sources import normalize_solarwinds_node, classify_solarwinds_health
    from app.repositories.decision_metrics import resource_value, resources
    normalized = normalize_solarwinds_node({'NodeID': 1, 'Status': 1, 'CPULoad': raw,
                                          'PercentMemoryUsed': raw, 'AvgResponseTime': 150})
    assert normalized['cpu_load'] == normalized['ram_used'] == resource_value(raw) == expected
    assert resources(normalized['attributes']) == (expected, expected)
    assert normalized['health_tier'] == classify_solarwinds_health('Up', raw, raw) == tier
    assert classify_solarwinds_health('Down', raw, raw) == 'Low'
    assert normalized['latency_ms'] == 150


async def seed(session, source, rows):
    for index, row in enumerate(rows):
        session.add(ConfigurationItem(
            source_system=source, source_id=str(index), name=f"node-{index}",
            ci_type="Server" if source == "SOLARWINDS" else "Windows",
            vendor="Microsoft", health_tier="High", **row,
        ))
    await session.flush()


@pytest.mark.asyncio
async def test_intune_reports_compliance_and_checkin_evidence(session):
    now = datetime.now(timezone.utc)
    await seed(session, "INTUNE", [
        {"status": "compliant", "attributes": {"last_sync_date_time": (now-timedelta(hours=2)).isoformat()}},
        {"status": "noncompliant", "attributes": {"last_sync_date_time": (now-timedelta(days=15)).isoformat()}},
        {"status": "inGracePeriod", "attributes": {}},
        {"status": "unknown", "attributes": {"last_sync_date_time": (now+timedelta(days=1)).isoformat()}},
    ])
    payload = await SummaryRepository(session).get_intune_summary()
    evidence = payload["decision_metrics"]
    metric = evidence["confirmed_compliance"]
    assert (metric["numerator"], metric["denominator"], metric["value"]) == (1, 4, 25)
    assert (metric["known_count"], metric["unknown_count"], metric["coverage_pct"]) == (3, 1, 75)
    assert evidence['compliance_state_counts']['in_grace_period'] == 1
    assert sum(evidence['compliance_state_counts'].values()) == 4
    recent = evidence["recent_checkins"]
    assert (recent["numerator"], recent["denominator"], recent["known_count"]) == (1, 4, 2)
    assert evidence["checkin_age_buckets"]["missing_or_invalid"] == 2
    assert sum(evidence["checkin_age_buckets"].values()) == 4
    assert metric["observed_at"] and "snapshot" in metric["measurement_window"]


@pytest.mark.asyncio
async def test_solarwinds_status_and_resource_evidence(session):
    await seed(session, "SOLARWINDS", [
        {"status": "Up", "attributes": {"cpu_load": 10, "memory_used": 20}},
        {"status": "Up", "attributes": {"cpu_load": 85}},
        {"status": "Down", "attributes": {"cpu_load": 101, "memory_used": "NaN"}},
        {"status": "Unknown", "attributes": {"cpu_load": True, "memory_used": -1}},
        {"status": "Unmanaged", "attributes": {"cpu_load": "Infinity", "memory_used": 95}},
    ])
    payload = await SummaryRepository(session).get_solarwinds_summary()
    evidence = payload["decision_metrics"]
    status = evidence["current_node_status"]
    assert (status["numerator"], status["denominator"], status["value"]) == (2, 4, 50)
    assert (status["known_count"], status["unknown_count"], status["coverage_pct"]) == (3, 1, 75)
    assert evidence["all_fleet_up"]["value"] == 40
    assert evidence["status_evidence"] == {"unknown_count": 1, "unmanaged_count": 1, "known_monitored_count": 3}
    assert evidence["cpu_coverage"]["numerator"] == 2
    assert evidence["memory_coverage"]["numerator"] == 2
    assert evidence["resource_health_counts"] == {"normal": 1, "elevated": 1, "critical": 1, "insufficient_data": 2}
    assert evidence["resource_pressure"]["numerator"] == 2
    assert evidence["resource_pressure"]["coverage_pct"] == 20
    saturated = payload["top_saturated_servers"]
    assert len(saturated) == 2
    assert saturated[0]["cpu_load"] is None
    assert saturated[1]["memory_used"] is None
    assert payload["metrics"]["availability_pct"] == 66.67  # legacy contract remains


@pytest.mark.asyncio
async def test_unmeasured_population_is_not_healthy(session):
    await seed(session, "SOLARWINDS", [{"status": "Unmanaged", "attributes": {}}])
    evidence = (await SummaryRepository(session).get_solarwinds_summary())["decision_metrics"]
    assert evidence["current_node_status"]["value"] is None
    assert evidence["resource_health_counts"]["normal"] == 0
    assert evidence["resource_health_counts"]["insufficient_data"] == 1
    assert evidence["resource_pressure"]["unknown_count"] == 1
    assert evidence["resource_pressure"]["value"] is None


@pytest.mark.parametrize('source', ['INTUNE','SOLARWINDS'])
async def test_retired_records_do_not_supply_decision_evidence(session, source):
    await seed(session, source, [
        {'status':'Up' if source == 'SOLARWINDS' else 'compliant', 'attributes':{}},
        {'status':'Up' if source == 'SOLARWINDS' else 'compliant', 'attributes':{}, 'is_active':False},
    ])
    repository = SummaryRepository(session)
    payload = await (repository.get_solarwinds_summary() if source == 'SOLARWINDS' else repository.get_intune_summary())
    metric = payload['decision_metrics']['current_node_status' if source == 'SOLARWINDS' else 'confirmed_compliance']
    assert metric['denominator'] == 1
