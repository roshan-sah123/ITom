import hashlib

import openpyxl
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def review_client(api_environment, tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "CMDB_INVENTORY_ADMIN_TOKEN", "test-only-token")
    from app.api.v1.endpoints.assets import get_asset_inventory_service
    from app.services.asset_inventory_service import AssetInventoryService
    workbook = openpyxl.Workbook()
    workbook.active.append(["HOST NAME", "Site"])
    workbook.active.append(["srv-01", "Delhi"])
    workbook.save(tmp_path / "server.xlsx")
    workbook.close()
    api_environment.dependency_overrides[get_asset_inventory_service] = lambda: AssetInventoryService(tmp_path)
    async with AsyncClient(transport=ASGITransport(app=api_environment, client=("127.0.0.1", 1234)),
                           base_url="http://127.0.0.1:8090", headers={"Origin": "http://127.0.0.1:8090", "Authorization": "Bearer test-only-token"}) as client:
        yield client, tmp_path


@pytest.mark.asyncio
async def test_cmdb_edit_review_create_delete_do_not_change_source_or_telemetry(review_client):
    client, directory = review_client
    before = hashlib.sha256((directory / "server.xlsx").read_bytes()).hexdigest()
    telemetry_before = (await client.get("/api/v1/cmdb/cis")).json()
    listed = await client.get("/api/v1/assets/records/server")
    assert listed.status_code == 200, listed.text
    record = listed.json()["items"][0]
    assert record["name"] == "srv-01" and record["revision"] == 1
    path = f'/api/v1/assets/records/server/{record["id"]}'
    reviewed = await client.post(path + "/fields/0/validate", json={"actor": "Reviewer", "expected_revision": 1})
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["field_reviews"]["0"]["validated_by"] == "Reviewer"
    validated = await client.post(path + "/validate", json={"actor": "Reviewer", "expected_revision": 2})
    assert validated.json()["is_validated"] is True
    data = validated.json()["data"]
    data[1]["value"] = "Pune"
    changed = await client.put(path, json={"actor": "Editor", "expected_revision": 3, "name": "srv-01", "data": data})
    assert changed.status_code == 200, changed.text
    assert changed.json()["is_validated"] is False
    assert set(changed.json()["field_reviews"]) == {"0"}
    assert (await client.post(path + "/validate", json={"actor": "Reviewer", "expected_revision": 3})).status_code == 409
    assert (await client.get("/api/v1/assets/inventory/server")).json()["items"][0]["Site"] == "Pune"
    assert (await client.get("/api/v1/assets/summary")).json()["items"][0]["total"] == 1
    created = await client.post("/api/v1/assets/records/server", json={
        "actor": "Editor", "name": "srv-02", "source_sheet": record["source_sheet"],
        "data": [{"index": 0, "header": "HOST NAME", "value": "srv-02"}, {"index": 1, "header": "Site", "value": "Noida"}],
    })
    assert created.status_code == 201, created.text
    removed = await client.request("DELETE", path, json={"actor": "Editor", "expected_revision": 4})
    assert removed.status_code == 204, removed.text
    assert (await client.get("/api/v1/assets/records/server?search=srv-01")).json()["total"] == 0
    assert (await client.get("/api/v1/assets/records/server")).json()["total"] == 1
    assert (await client.get("/api/v1/cmdb/cis")).json() == telemetry_before
    assert hashlib.sha256((directory / "server.xlsx").read_bytes()).hexdigest() == before


@pytest.mark.asyncio
async def test_cmdb_write_guards_headers_limits_and_missing_sources(review_client):
    client, _ = review_client
    assert (await client.post("/api/v1/assets/records/server", json={}, headers={"Origin": "http://evil.example"})).status_code == 403
    assert (await client.get("/api/v1/assets/records/network")).status_code == 503
    record = (await client.get("/api/v1/assets/records/server")).json()["items"][0]
    path = f'/api/v1/assets/records/server/{record["id"]}'
    wrong = [{"index": 0, "header": "Changed header", "value": "bad"}, {"index": 1, "header": "Site", "value": "bad"}]
    assert (await client.put(path, json={"actor": "Editor", "expected_revision": 1, "name": "srv-01", "data": wrong})).status_code == 422
    assert (await client.post(path + "/fields/20/validate", json={"actor": "Reviewer", "expected_revision": 1})).status_code == 422
    assert (await client.post(path + "/validate", content=b"x" * (256 * 1024 + 1), headers={"Content-Type": "application/json"})).status_code == 413
    assert (await client.post(path + "/validate", content="not JSON")).status_code == 415


@pytest.mark.asyncio
async def test_cmdb_production_token_and_empty_inventory_do_not_reseed(review_client, monkeypatch, api_environment):
    from app.core.config import settings
    client, _ = review_client
    record = (await client.get("/api/v1/assets/records/server")).json()["items"][0]
    path = f'/api/v1/assets/records/server/{record["id"]}'
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "CMDB_INVENTORY_ADMIN_TOKEN", None)
    assert (await client.get("/api/v1/assets/admin/check")).status_code == 503
    monkeypatch.setattr(settings, "CMDB_INVENTORY_ADMIN_TOKEN", "test-only-token")
    assert (await client.get("/api/v1/assets/admin/check", headers={"Authorization": ""})).status_code == 401
    assert (await client.get("/api/v1/assets/admin/check", headers={"Authorization": "Bearer test-only-token"})).status_code == 200
    removed = await client.request("DELETE", path, headers={"Authorization": "Bearer test-only-token"},
        json={"actor": "Editor", "expected_revision": 1})
    assert removed.status_code == 204
    assert (await client.get("/api/v1/assets/records/server")).json()["total"] == 0
    assert (await client.get("/api/v1/assets/inventory/server")).json()["total"] == 0
    summary = (await client.get("/api/v1/assets/summary")).json()["items"][0]
    assert summary["data_available"] is True and summary["total"] == 0
    async with AsyncClient(transport=ASGITransport(app=api_environment, client=("10.0.0.1", 1234)),
                           base_url="http://127.0.0.1:8090") as remote:
        assert (await remote.get("/api/v1/assets/records/server")).status_code == 403


@pytest.mark.asyncio
async def test_cmdb_sensitive_operations_locked_without_key_in_development(review_client, monkeypatch):
    from app.core.config import settings
    client, _ = review_client
    row = (await client.get("/api/v1/assets/records/server")).json()["items"][0]
    path = f'/api/v1/assets/records/server/{row["id"]}'
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "CMDB_INVENTORY_ADMIN_TOKEN", None)
    for method, suffix, body in [
        ("PUT", "", {"actor": "Editor", "name": row["name"], "data": row["data"], "expected_revision": 1}),
        ("POST", "/validate", {"actor": "Reviewer", "expected_revision": 1}),
        ("POST", "/fields/0/validate", {"actor": "Reviewer", "expected_revision": 1}),
        ("DELETE", "", {"actor": "Editor", "expected_revision": 1}),
    ]:
        assert (await client.request(method, path + suffix, json=body)).status_code == 503
