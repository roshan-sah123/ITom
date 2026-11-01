import base64
import io

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image


@pytest.fixture
async def vendor_client(api_environment, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "CMDB_INVENTORY_ADMIN_TOKEN", "test-only-key")
    async with AsyncClient(
        transport=ASGITransport(app=api_environment, client=("127.0.0.1", 12345)),
        base_url="http://127.0.0.1:8090",
        headers={"Origin": "http://127.0.0.1:8090", "Authorization": "Bearer test-only-key"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_vendor_sensitive_operations_require_shared_key(vendor_client, monkeypatch):
    from app.core.config import settings
    client = vendor_client
    row = (await client.post("/api/v1/vendors/submissions", json=submission())).json()
    path = f'/api/v1/vendors/submissions/{row["id"]}'
    for key, status in [(None, 503), ("test-only-key", 401)]:
        monkeypatch.setattr(settings, "CMDB_INVENTORY_ADMIN_TOKEN", key)
        for method, suffix, body in [
            ("PUT", "", {**submission(), "expected_revision": 1}),
            ("POST", "/validate", {"reviewer": "Reviewer", "expected_revision": 1}),
            ("DELETE", "?expected_revision=1", None),
        ]:
            response = await client.request(method, path + suffix, json=body, headers={"Authorization": "Bearer wrong-key"})
            assert response.status_code == status
    assert (await client.get(path)).json()["revision"] == 1


def submission(request_id="a" * 32):
    return {
        "request_id": request_id,
        "vendor": "Example partner",
        "method": "Portal",
        "steps": [{"what_to_do": "Open support", "how_to_do": "Sign in", "image": None}],
        "sop": None,
    }


@pytest.mark.asyncio
async def test_vendor_serials_close_deleted_gaps_without_rewriting_ids(vendor_client):
    client = vendor_client
    rows = []
    for index in range(3):
        rows.append((await client.post("/api/v1/vendors/submissions", json={
            **submission(str(index + 1) * 32), "vendor": f"Partner {index}",
        })).json())
    assert (await client.delete(f'/api/v1/vendors/submissions/{rows[0]["id"]}?expected_revision=1')).status_code == 204
    listed = (await client.get("/api/v1/vendors/submissions")).json()
    assert [row["serial"] for row in listed["items"]] == [1, 2]
    assert [row["id"] for row in listed["items"]] == [rows[1]["id"], rows[2]["id"]]
    assert listed["next_serial"] == 3
    assert (await client.get(f'/api/v1/vendors/submissions/{rows[2]["id"]}')).json()["serial"] == 2
    filtered = (await client.get("/api/v1/vendors/submissions?search=Partner%202")).json()
    assert filtered["items"][0]["serial"] == 2
    paged = (await client.get("/api/v1/vendors/submissions?page=2&page_size=1")).json()
    assert paged["items"][0]["serial"] == 2
    next_row = (await client.post("/api/v1/vendors/submissions", json=submission("d" * 32))).json()
    assert next_row["serial"] == 3


@pytest.mark.asyncio
async def test_vendor_submission_lifecycle_and_revision_guards(vendor_client):
    client = vendor_client
    body = submission()
    created = await client.post("/api/v1/vendors/submissions", json=body)
    assert created.status_code == 201, created.text
    item = created.json()
    identifier = item["id"]
    assert item["validation"] == "Pending"
    assert item["validated_by"] is None
    assert item["step_count"] == 1
    assert (await client.post("/api/v1/vendors/submissions", json=body)).json()["id"] == identifier
    body["vendor"] = "Changed request"
    assert (await client.post("/api/v1/vendors/submissions", json=body)).status_code == 409

    validated = await client.post(
        f"/api/v1/vendors/submissions/{identifier}/validate",
        json={"reviewer": "Reviewer", "expected_revision": 1},
    )
    assert validated.status_code == 200
    assert validated.json()["validated_by"] == "Reviewer"
    assert validated.json()["validated_on"]
    edit = {**submission(), "vendor": "Updated partner", "expected_revision": 2}
    edited = await client.put(f"/api/v1/vendors/submissions/{identifier}", json=edit)
    assert edited.status_code == 200, edited.text
    assert edited.json()["validation"] == "Pending"
    assert edited.json()["validated_by"] is None
    assert (await client.put(f"/api/v1/vendors/submissions/{identifier}", json=edit)).status_code == 409
    detail = await client.get(f"/api/v1/vendors/submissions/{identifier}")
    assert detail.json()["steps"][0]["how_to_do"] == "Sign in"
    assert (await client.delete(f"/api/v1/vendors/submissions/{identifier}?expected_revision=2")).status_code == 409
    assert (await client.delete(f"/api/v1/vendors/submissions/{identifier}?expected_revision=3")).status_code == 204
    assert (await client.get(f"/api/v1/vendors/submissions/{identifier}")).status_code == 404
    assert (await client.get("/api/v1/vendors/submissions")).json()["total"] == 0
    assert (await client.post("/api/v1/vendors/submissions", json=submission())).status_code == 409


@pytest.mark.asyncio
async def test_vendor_sop_optional_and_download_is_safe(vendor_client):
    body = submission("b" * 32)
    body["sop"] = {"name": "guide.txt", "data": base64.b64encode(b"Support instructions").decode()}
    result = await vendor_client.post("/api/v1/vendors/submissions", json=body)
    assert result.status_code == 201, result.text
    identifier = result.json()["id"]
    download = await vendor_client.get(f"/api/v1/vendors/submissions/{identifier}/sop")
    assert download.content == b"Support instructions"
    assert download.headers["content-disposition"].startswith("attachment;")
    body["request_id"] = "c" * 32
    body["sop"] = {"name": "guide.txt", "data": base64.b64encode(b"<script>unsafe</script>").decode()}
    assert (await vendor_client.post("/api/v1/vendors/submissions", json=body)).status_code == 422


@pytest.mark.asyncio
async def test_vendor_images_and_empty_steps_are_validated(vendor_client):
    body = submission()
    body["steps"] = []
    assert (await vendor_client.post("/api/v1/vendors/submissions", json=body)).status_code == 422
    body = submission()
    body["steps"][0]["image"] = {
        "name": "fake.png", "data": base64.b64encode(b"not an image").decode(),
    }
    assert (await vendor_client.post("/api/v1/vendors/submissions", json=body)).status_code == 422


@pytest.mark.asyncio
async def test_vendor_images_and_sop_survive_edit_and_are_removed_on_delete(vendor_client):
    content = io.BytesIO()
    Image.new("RGB", (2, 2)).save(content, format="PNG")
    body = submission()
    body["steps"][0]["image"] = {"name": "step.png", "data": base64.b64encode(content.getvalue()).decode()}
    body["sop"] = {"name": "guide.txt", "data": base64.b64encode(b"Instructions").decode()}
    result = await vendor_client.post("/api/v1/vendors/submissions", json=body)
    assert result.status_code == 201, result.text
    identifier = result.json()["id"]
    files = (await vendor_client.get(f"/api/v1/vendors/submissions/{identifier}?include_files=true")).json()
    assert files["draft"]["steps"][0]["image"] == body["steps"][0]["image"]
    edit_body = {
        **files["draft"], "request_id": "d" * 32, "expected_revision": 1, "sop": files["sop_file"],
    }
    assert (await vendor_client.put(f"/api/v1/vendors/submissions/{identifier}", json=edit_body)).status_code == 200
    image = await vendor_client.get(f"/api/v1/vendors/submissions/{identifier}/images/0")
    assert image.content == content.getvalue()
    assert image.headers["content-type"] == "image/png"
    assert (await vendor_client.get(f"/api/v1/vendors/submissions/{identifier}/images/1")).status_code == 404
    assert (await vendor_client.get("/api/v1/vendors/submissions?search=%")).json()["total"] == 0
    assert (await vendor_client.delete(f"/api/v1/vendors/submissions/{identifier}?expected_revision=2")).status_code == 204
    assert (await vendor_client.get(f"/api/v1/vendors/submissions/{identifier}/images/0")).status_code == 404
    assert (await vendor_client.get(f"/api/v1/vendors/submissions/{identifier}/sop")).status_code == 404


@pytest.mark.asyncio
async def test_vendor_routes_reject_nonlocal_and_cross_origin_requests(api_environment, vendor_client):
    async with AsyncClient(
        transport=ASGITransport(app=api_environment, client=("10.0.0.1", 1234)),
        base_url="http://127.0.0.1:8090",
    ) as remote:
        assert (await remote.get("/api/v1/vendors/submissions")).status_code == 403
    assert (await vendor_client.post(
        "/api/v1/vendors/submissions", json=submission(), headers={"Origin": "http://evil.example"},
    )).status_code == 403
    assert (await vendor_client.post(
        "/api/v1/vendors/submissions", json=submission(), headers={"Sec-Fetch-Site": "cross-site"},
    )).status_code == 403
