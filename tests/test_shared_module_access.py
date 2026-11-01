"""Remote module access must not grant administration or affect telemetry."""
import pytest
import base64
import openpyxl
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def remote_client(api_environment, monkeypatch):
    from app.core.config import settings
    monkeypatch.setitem(settings.__dict__, "MODULE_SHARED_ORIGIN", "https://itom.example.test")
    monkeypatch.setitem(settings.__dict__, "MODULE_SHARED_ACCESS_KEY", "test-access-key")
    monkeypatch.setitem(settings.__dict__, "MODULE_NETWORK_ACCESS", False)
    monkeypatch.setattr(settings, "SECRET_KEY", "test-session-secret-at-least-32-characters")
    monkeypatch.setattr(settings, "CMDB_INVENTORY_ADMIN_TOKEN", "test-admin-key")
    async with AsyncClient(transport=ASGITransport(app=api_environment, client=("10.0.0.5", 1234)),
                           base_url="https://itom.example.test",
                           headers={"Origin": "https://itom.example.test", "Sec-Fetch-Site": "same-origin"}) as client:
        yield client


@pytest.mark.asyncio
async def test_remote_shared_data_requires_access_session_not_admin_key(remote_client):
    client = remote_client
    paths = ("/api/v1/vendors/submissions", "/api/v1/knowledge/content", "/api/v1/assets/summary")
    for path in paths:
        assert (await client.get(path)).status_code == 401
    assert (await client.post("/api/v1/modules/access", json={"key": "test-admin-key"})).status_code == 401
    response = await client.post("/api/v1/modules/access", json={"key": "test-access-key"})
    assert response.status_code == 200, response.text
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=strict" in cookie
    assert "test-access-key" not in cookie
    assert (await client.get("/api/v1/modules/access")).json()["authorized"] is True
    assert (await client.get(paths[0])).status_code == 200
    assert (await client.get(paths[1])).status_code == 200
    # Sensitive operations require the separate administration key even after login.
    path = "/api/v1/vendors/submissions/2147483647/validate"
    body = {"reviewer": "Reviewer", "expected_revision": 1}
    assert (await client.post(path, json=body)).status_code == 401
    assert (await client.post(path, json=body, headers={"Authorization": "Bearer test-access-key"})).status_code == 401
    assert (await client.post(path, json=body, headers={"Authorization": "Bearer test-admin-key"})).status_code == 404
    assert (await client.get("/api/v1/cmdb/cis")).status_code == 200
    assert (await client.delete("/api/v1/modules/access")).status_code == 204
    assert (await client.get(paths[0])).status_code == 401


@pytest.mark.asyncio
async def test_remote_origin_tamper_expiry_and_rotation(remote_client, monkeypatch):
    from app.core.config import settings
    client = remote_client
    assert (await client.post("/api/v1/modules/access", json={"key": "test-access-key"},
                             headers={"Origin": "https://evil.example"})).status_code == 403
    assert (await client.post("/api/v1/modules/access", json={"key": "test-access-key"},
                             headers={"Sec-Fetch-Site": "cross-site"})).status_code == 403
    await client.post("/api/v1/modules/access", json={"key": "test-access-key"})
    cookie = client.cookies.get("itom_module_access")
    client.cookies.clear()
    client.cookies.set("itom_module_access", cookie[:-1] + ("0" if cookie[-1] != "0" else "1"))
    assert (await client.get("/api/v1/vendors/submissions")).status_code == 401
    client.cookies.clear()
    client.cookies.set("itom_module_access", cookie)
    assert (await client.get("/api/v1/vendors/submissions", headers={"Host": "unapproved.example"})).status_code == 403
    monkeypatch.setattr(settings, "MODULE_SHARED_ACCESS_KEY", "rotated-key")
    assert (await client.get("/api/v1/vendors/submissions")).status_code == 401
    monkeypatch.setattr(settings, "MODULE_SHARED_ACCESS_KEY", "test-access-key")
    from app.api.v1.endpoints import module_access
    monkeypatch.setattr(module_access.time, "time", lambda: 99999999999)
    assert (await client.get("/api/v1/vendors/submissions")).status_code == 401


@pytest.mark.parametrize("overrides", [
    {"MODULE_SHARED_ORIGIN": "http://itom.example.test"},
    {"MODULE_SHARED_ORIGIN": "https://itom.example.test/path"},
    {"MODULE_SHARED_ACCESS_KEY": ""},
    {"MODULE_SHARED_ACCESS_KEY": "shared-test-key", "CMDB_INVENTORY_ADMIN_TOKEN": "shared-test-key"},
])
def test_shared_access_configuration_rejects_invalid_origin_missing_and_reused_keys(overrides):
    from app.core.config import Settings
    from pydantic import ValidationError
    values = {"MODULE_SHARED_ORIGIN": "https://itom.example.test", "MODULE_SHARED_ACCESS_KEY": "test-access-key",
              "SECRET_KEY": "isolated-session-signing-key", "APP_ENV": "testing"}
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **(values | overrides))


def test_network_access_configuration_requires_domain_but_not_shared_key():
    from app.core.config import Settings
    from pydantic import ValidationError
    settings = Settings(_env_file=None, APP_ENV="testing", MODULE_NETWORK_ACCESS=True,
                        MODULE_SHARED_ORIGIN="https://itom.example.test", MODULE_SHARED_ACCESS_KEY=None)
    assert settings.MODULE_NETWORK_ACCESS
    with pytest.raises(ValidationError):
        Settings(_env_file=None, APP_ENV="testing", MODULE_NETWORK_ACCESS=True, MODULE_SHARED_ORIGIN="")


@pytest.mark.parametrize("network_access", [False, True])
@pytest.mark.asyncio
async def test_shared_submissions_workbook_additions_and_files_visible_to_another_browser(remote_client, api_environment, tmp_path, monkeypatch, network_access):
    from app.core.config import settings
    monkeypatch.setitem(settings.__dict__, "MODULE_NETWORK_ACCESS", network_access)
    from app.api.v1.endpoints.assets import get_asset_inventory_service
    from app.services.asset_inventory_service import AssetInventoryService
    book = openpyxl.Workbook()
    book.active.append(["HOST NAME", "Site"])
    book.active.append(["workbook-host", "Site"])
    book.save(tmp_path / "server.xlsx")
    book.close()
    api_environment.dependency_overrides[get_asset_inventory_service] = lambda: AssetInventoryService(tmp_path)
    client = remote_client
    if not network_access:
        await client.post("/api/v1/modules/access", json={"key": "test-access-key"})
    vendor = await client.post("/api/v1/vendors/submissions", json={
        "request_id": "a" * 32, "vendor": "Shared partner", "method": "Portal",
        "steps": [{"what_to_do": "Open", "how_to_do": "Sign in", "image": None}], "sop": None,
    })
    assert vendor.status_code == 201, vendor.text
    content = await client.post("/api/v1/knowledge/content", json={
        "request_id": "b" * 32, "name": "Shared content", "description": "Guide", "category": "Runbook",
        "file": {"name": "guide.txt", "type": "text/plain", "data": base64.b64encode(b"Shared file bytes").decode()},
    })
    assert content.status_code == 201, content.text
    seeded = (await client.get("/api/v1/assets/records/server")).json()
    created = await client.post("/api/v1/assets/records/server", json={
        "actor": "Contributor", "name": "user-host", "source_sheet": seeded["source_sheet"],
        "data": [{"index": 0, "header": "HOST NAME", "value": "user-host"}, {"index": 1, "header": "Site", "value": "Other"}],
    })
    assert created.status_code == 201, created.text
    async with AsyncClient(transport=ASGITransport(app=api_environment, client=("10.0.0.6", 1234)),
                           base_url="https://itom.example.test", headers={"Origin": "https://itom.example.test"}) as other:
        file_path = f'/api/v1/knowledge/content/{content.json()["id"]}/file'
        if not network_access:
            assert (await other.get(file_path)).status_code == 401
            await other.post("/api/v1/modules/access", json={"key": "test-access-key"})
        assert (await other.get(file_path)).content == b"Shared file bytes"
        assert (await other.get("/api/v1/vendors/submissions")).json()["items"][0]["vendor"] == "Shared partner"
        assert (await other.get("/api/v1/knowledge/content")).json()["items"][0]["name"] == "Shared content"
        assert (await other.get("/api/v1/assets/records/server")).json()["total"] == 2
        assert (await other.get("/api/v1/assets/summary")).json()["items"][0]["total"] == 2


@pytest.mark.asyncio
async def test_network_access_retains_admin_origin_and_host_guards(remote_client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setitem(settings.__dict__, "MODULE_NETWORK_ACCESS", True)
    monkeypatch.setattr(settings, "MODULE_SHARED_ACCESS_KEY", None)
    client = remote_client
    result = await client.get("/api/v1/modules/access")
    assert result.json() == {"authorized": True, "local": False, "network": True}
    assert "set-cookie" not in result.headers
    for path in ["/api/v1/vendors/submissions", "/api/v1/knowledge/content"]:
        assert (await client.get(path)).status_code == 200
        assert (await client.post(path, json={}, headers={"Origin": "https://other.example"})).status_code == 403
        assert (await client.get(path, headers={"Host": "other.example"})).status_code == 403
    for path in ["/api/v1/vendors/submissions/2147483647/validate", "/api/v1/knowledge/content/2147483647/validate"]:
        body = {"reviewer": "Operator", "expected_revision": 1}
        assert (await client.post(path, json=body)).status_code == 401
        assert (await client.post(path, json=body, headers={"Authorization": "Bearer wrong-key"})).status_code == 401
        assert (await client.post(path, json=body, headers={"Authorization": "Bearer test-admin-key"})).status_code == 404
    assert (await client.get("/api/v1/assets/admin/check")).status_code == 401
    assert (await client.get("/api/v1/assets/admin/check", headers={"Authorization": "Bearer test-admin-key"})).status_code == 200
    monkeypatch.setattr(settings, "CMDB_INVENTORY_ADMIN_TOKEN", None)
    assert (await client.get("/api/v1/assets/admin/check")).status_code == 503
