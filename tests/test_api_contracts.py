"""PRD inventory, source-backed summaries, probes, freshness and sync audit contracts."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.api.v1.endpoints import sync as sync_routes
from tests.factories import make_ci, make_run

LIST_ROUTES = ["cmdb/cis", "intune/devices", "solarwinds/nodes", "solarwinds/network-devices"]


async def test_sync_audit_hides_stored_private_diagnostics(api_client, session):
    from app.models.sync import SyncErrorLog

    run = make_run("INTUNE", "FAILED")
    session.add(run)
    await session.flush()
    session.add(SyncErrorLog(
        sync_run_id=run.id, error_code="RuntimeError",
        error_message="private-diagnostic database connection failed",
        stack_trace="Traceback private-diagnostic C:/internal/service.py",
        context_data={"connection": "private-diagnostic"},
    ))
    await session.commit()
    for path in ["/runs", "/runs/latest", f"/runs/{run.id}"]:
        response = await api_client.get("/api/v1/sync" + path)
        assert response.status_code == 200
        assert "private-diagnostic" not in response.text
        data = response.json()
        error = (data[0] if isinstance(data, list) else data)["error_logs"][0]
        assert error["error_code"] == "RuntimeError"
        assert error["stack_trace"] is None
        assert error["context_data"] == {}


@pytest.fixture
async def inventory(session):
    records = [
        make_ci("SOLARWINDS", "PUNE-SERVER", "Up", "High", location="Pune"),
        make_ci("SOLARWINDS", "NOIDA-SERVER", "Critical", "Low", location="Noida"),
        make_ci("SOLARWINDS", "PUNE-SWITCH", "Down", "Low", ci_type="Switch", vendor="Cisco", location="Pune"),
        make_ci("INTUNE", "LAPTOP-OK", "Compliant", "High", ci_type="Windows"),
        make_ci("INTUNE", "LAPTOP-RISK", "Noncompliant", "Low", ci_type="Windows"),
        make_ci("INTUNE", "RETIRED-LAPTOP", "Compliant", "High", is_active=False),
    ]
    session.add_all(records)
    await session.commit()
    return records


async def test_portal_and_probe_states(api_client, db_engine):
    portal = await api_client.get("/")
    assert portal.status_code == 200 and "text/html" in portal.headers["content-type"]
    assert "Coforge ITOM Operations Portal" in portal.text
    assert (await api_client.get("/healthz")).json()["status"] == "ok"
    assert (await api_client.get("/ready")).json()["status"] == "ready"
    async with db_engine.begin() as conn:
        await conn.execute(text("UPDATE alembic_version SET version_num = 'obsolete'"))
    readiness = await api_client.get("/ready")
    assert readiness.status_code == 503 and readiness.json()["migration_head"] is False
    assert (await api_client.get("/healthz")).status_code == 200


@pytest.mark.parametrize("route", ["intune", "solarwinds"])
async def test_no_ingestion_means_unavailable_summary(api_client, route):
    response = await api_client.get(f"/api/v1/{route}/summary")
    assert response.status_code == 503
    assert response.json()["data_source"] == "NONE"


async def test_empty_cmdb_is_explicitly_unavailable(api_client):
    response = await api_client.get("/api/v1/cmdb/summary")
    assert response.status_code == 200
    assert response.json()["total_cis"] == 0 and response.json()["data_available"] is False
    assert response.json()["compliance_rate_pct"] is None


async def test_source_summaries_reconcile_to_active_inventory(api_client, inventory):
    cmdb = (await api_client.get("/api/v1/cmdb/summary")).json()
    intune = (await api_client.get("/api/v1/intune/summary")).json()
    solarwinds = (await api_client.get("/api/v1/solarwinds/summary")).json()
    assert cmdb["total_cis"] == 5
    assert intune["metrics"]["total_managed_devices"] == 2
    assert intune["metrics"]["compliance_rate_pct"] == 50
    assert sum(intune["compliance_breakdown"].values()) == 2
    assert solarwinds["metrics"]["total_nodes"] == 3
    assert solarwinds["metrics"]["server_nodes_count"] == 2
    assert sum(solarwinds["status_breakdown"].values()) == 3


@pytest.mark.parametrize("route", LIST_ROUTES)
@pytest.mark.parametrize("size", [10, 25, 50, 100])
async def test_inventory_pagination_is_bounded(api_client, inventory, route, size):
    response = await api_client.get(f"/api/v1/{route}", params={"page_size": size})
    assert response.status_code == 200
    data = response.json()
    assert data["page_size"] == size and len(data["items"]) <= size
    assert all(row["is_active"] for row in data["items"])
    assert all(isinstance(row["id"], str) and row["last_sync_time"].endswith("+00:00") for row in data["items"])


@pytest.mark.parametrize("route", LIST_ROUTES)
@pytest.mark.parametrize("params", [{"page": 0}, {"page": -1}, {"page_size": 0}, {"page_size": 15}, {"page_size": 101}, {"page_size": "foo"}])
async def test_invalid_inventory_pagination_rejected(api_client, route, params):
    assert (await api_client.get(f"/api/v1/{route}", params=params)).status_code == 422


async def test_inventory_filters_sorting_and_location_scope(api_client, inventory):
    data = (await api_client.get("/api/v1/cmdb/cis", params={"source_system": "SOLARWINDS", "location": " pune ", "sort_by": "name", "sort_order": "desc"})).json()
    assert data["total"] == 2
    assert [row["name"] for row in data["items"]] == ["PUNE-SWITCH", "PUNE-SERVER"]
    network = (await api_client.get("/api/v1/solarwinds/network-devices")).json()
    assert network["total"] == 1 and network["items"][0]["name"] == "PUNE-SWITCH"
    page = (await api_client.get("/api/v1/cmdb/cis", params={"page": 999})).json()
    assert page["total"] == 5 and page["items"] == []


@pytest.mark.parametrize("payload", ["' OR '1'='1", "'; DROP TABLE configuration_items; --", "<script>alert(1)</script>", "../../etc/passwd", "\x00\x01", "A" * 2048])
async def test_hostile_search_does_not_expand_inventory_or_mutate_data(api_client, inventory, payload):
    response = await api_client.get("/api/v1/cmdb/cis", params={"search": payload})
    assert response.status_code == 200 and response.json()["total"] == 0
    assert (await api_client.get("/api/v1/cmdb/cis")).json()["total"] == 5


@pytest.mark.parametrize("route", LIST_ROUTES)
@pytest.mark.parametrize("payload", ["\x00", "PUNE\x00unrelated", " \x00 "])
async def test_nul_search_never_matches_unrelated_assets(api_client, inventory, route, payload):
    response = await api_client.get(f"/api/v1/{route}", params={"search": payload})
    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert response.json()["items"] == []


@pytest.mark.parametrize("route", LIST_ROUTES)
@pytest.mark.parametrize("failed_query", [1, 2])
async def test_inventory_datastore_outage_returns_503(api_client, session, inventory, monkeypatch, route, failed_query):
    from app.api.deps import get_ci_repository
    from app.main import app
    from app.repositories.ci_repository import CIRepository

    original_execute = session.execute
    calls = 0

    async def failing_execute(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == failed_query:
            raise OperationalError("SELECT private_inventory", {}, RuntimeError("private database details"))
        return await original_execute(*args, **kwargs)

    monkeypatch.setattr(session, "execute", failing_execute)
    app.dependency_overrides[get_ci_repository] = lambda: CIRepository(session)
    response = await api_client.get(f"/api/v1/{route}")
    assert response.status_code == 503
    assert response.json() == {"error": "Inventory datastore unavailable", "data_available": False}
    assert "private" not in response.text
    assert response.headers["X-Content-Type-Options"] == "nosniff"


async def test_detail_history_and_unknown_identity(api_client, inventory):
    identity = str(inventory[0].id)
    response = await api_client.get(f"/api/v1/cmdb/cis/{identity}")
    assert response.status_code == 200 and response.json()["id"] == identity
    assert (await api_client.get(f"/api/v1/cmdb/cis/{identity}/history")).json() == []
    assert (await api_client.get(f"/api/v1/cmdb/cis/{identity}/relationships")).json() == []
    assert (await api_client.get("/api/v1/cmdb/cis/not-a-uuid")).status_code == 404
    assert (await api_client.get(f"/api/v1/cmdb/cis/{inventory[-1].id}")).status_code == 404


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("route", ["cmdb/cis", "intune/devices", "solarwinds/nodes"])
async def test_inventory_is_read_only(api_client, method, route):
    response = await api_client.request(method, f"/api/v1/{route}", json={"name": "injected"})
    assert response.status_code == 405
    assert response.headers["allow"] == "GET, HEAD, OPTIONS"


async def test_freshness_unknown_has_no_fabricated_timestamp(api_client):
    report = (await api_client.get("/api/v1/system/freshness")).json()
    assert report["overall_status"] == "UNKNOWN"
    assert all(value["last_synchronized_at"] is None for value in report["sources"].values())
    response = await api_client.get("/healthz")
    assert response.headers["X-Sync-Status"] == "UNKNOWN"
    assert "X-Last-Synchronized-At" not in response.headers


@pytest.mark.parametrize("age_minutes,sw_status,intune_status,expected", [(0,"SUCCESS","SUCCESS","HEALTHY"), (60,"SUCCESS","SUCCESS","DEGRADED"), (0,"FAILED","SUCCESS","DEGRADED"), (0,"FAILED","FAILED","FAILED")])
async def test_sync_attempt_states_remain_truthful(api_client, session, age_minutes, sw_status, intune_status, expected):
    at = datetime.now(timezone.utc) - timedelta(minutes=age_minutes)
    session.add_all([make_run("SOLARWINDS", sw_status, at), make_run("INTUNE", intune_status, at)])
    await session.commit()
    response = await api_client.get("/api/v1/sync/status")
    assert response.status_code == 200 and response.json()["sync_state"] == expected
    assert response.json()["last_sync"].endswith("+00:00")


async def test_failed_attempt_does_not_advance_successful_freshness(api_client, session):
    old = datetime.now(timezone.utc) - timedelta(hours=1)
    session.add_all([make_run("SOLARWINDS", at=old), make_run("INTUNE", at=old), make_run("SOLARWINDS", "FAILED")])
    await session.commit()
    report = (await api_client.get("/api/v1/system/freshness")).json()
    assert report["overall_status"] == "STALE"
    assert report["sources"]["SOLARWINDS"]["age_seconds"] >= 3600


async def test_audit_run_serialization_and_source_filter(api_client, session):
    sw, intune = make_run("SOLARWINDS"), make_run("INTUNE")
    session.add_all([sw, intune])
    await session.commit()
    runs = (await api_client.get("/api/v1/sync/runs", params={"page_size": 1})).json()
    assert len(runs) == 1 and isinstance(runs[0]["id"], str)
    latest = (await api_client.get("/api/v1/sync/runs/latest", params={"source_system": "SOLARWINDS"})).json()
    assert latest["id"] == str(sw.id)
    assert (await api_client.get(f"/api/v1/sync/runs/{sw.id}")).json()["source_system"] == "SOLARWINDS"
    assert (await api_client.get("/api/v1/sync/runs/not-a-uuid")).status_code == 404


@pytest.mark.parametrize("scope", ["ALL", "INTUNE", "SOLARWINDS"])
async def test_manual_sync_dispatches_valid_scope_without_source_calls(api_client, monkeypatch, scope):
    task = AsyncMock()
    monkeypatch.setattr(sync_routes, "run_manual_sync", task)
    response = await api_client.post("/api/v1/sync/trigger", params={"source_system": scope})
    assert response.status_code == 202
    task.assert_awaited_once_with(scope)


async def test_manual_sync_rejects_unknown_scope(api_client, monkeypatch):
    task = AsyncMock()
    monkeypatch.setattr(sync_routes, "run_manual_sync", task)
    assert (await api_client.post("/api/v1/sync/trigger", params={"source_system": "OTHER"})).status_code == 422
    task.assert_not_awaited()


async def test_background_sync_persists_inventory_and_audit_in_owned_session(api_client, monkeypatch):
    from app.services import sync_service

    class TestSource:
        name = "INTUNE"
        snapshot_complete = False

        def fetch(self):
            return [{"external_id": "background-device", "name": "BACKGROUND-LAPTOP",
                     "status": "Compliant", "health_tier": "High", "ci_type": "Windows"}]

    monkeypatch.setattr(sync_service, "build_sources", lambda scope, offline=False: [TestSource()])
    response = await api_client.post("/api/v1/sync/trigger", params={"source_system": "INTUNE"})
    assert response.status_code == 202
    inventory = (await api_client.get("/api/v1/intune/devices")).json()
    assert inventory["total"] == 1 and inventory["items"][0]["name"] == "BACKGROUND-LAPTOP"
    audit = (await api_client.get("/api/v1/sync/runs/latest")).json()
    assert audit["status"] == "SUCCESS" and audit["source_system"] == "INTUNE"
    assert audit["records_processed"] == 1
    identity = inventory["items"][0]["id"]
    history = (await api_client.get(f"/api/v1/cmdb/cis/{identity}/history")).json()
    assert len(history) == 1 and history[0]["status"] == "Compliant"


async def test_successful_sources_provide_oldest_freshness_and_security_headers(api_client, session):
    session.add_all([make_run("SOLARWINDS", at=datetime.now(timezone.utc) - timedelta(minutes=2)), make_run("INTUNE")])
    await session.commit()
    response = await api_client.get("/healthz")
    assert response.headers["X-Sync-Status"] == "FRESH"
    assert int(response.headers["X-Data-Age-Seconds"]) >= 120
    assert response.headers["X-Last-Synchronized-At"].endswith("+00:00")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


async def test_idle_sync_and_disabled_scheduler_are_explicit(api_client):
    assert (await api_client.get("/api/v1/sync/status")).json()["sync_state"] == "IDLE"
    scheduler = (await api_client.get("/api/v1/sync/scheduler")).json()
    assert scheduler["enabled"] is False and scheduler["running"] is False
    assert scheduler["next_run"] is None
    assert (await api_client.get("/api/v1/sync/runs/latest")).status_code == 404


@pytest.mark.parametrize("origin,expected", [("http://localhost:8080", 200), ("https://untrusted.invalid", 400)])
async def test_cors_preflight_enforces_origin_allowlist(api_client, origin, expected):
    response = await api_client.options("/api/v1/cmdb/cis", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
    assert response.status_code == expected
    if expected == 200:
        assert response.headers["Access-Control-Allow-Origin"] == origin
    else:
        assert "Access-Control-Allow-Origin" not in response.headers


async def test_site_catalog_reconciles_with_location_filtered_inventory(api_client, inventory):
    response = await api_client.get("/api/v1/solarwinds/sites")
    assert response.status_code == 200
    sites = response.json()["data"]["items"]
    assert {site["name"] for site in sites} == {"Pune", "Noida"}
    assert sum(site["total_nodes"] for site in sites) == 3
    for site in sites:
        devices = (await api_client.get("/api/v1/solarwinds/nodes", params={"location": site["name"]})).json()
        assert devices["total"] == site["total_nodes"]
