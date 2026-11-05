import base64
import io
from zipfile import ZipFile

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def knowledge_client(api_environment, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "CMDB_INVENTORY_ADMIN_TOKEN", "test-only-key")
    async with AsyncClient(transport=ASGITransport(app=api_environment, client=("127.0.0.1", 1234)),
                           base_url="http://127.0.0.1:8090", headers={"Origin": "http://127.0.0.1:8090", "Authorization": "Bearer test-only-key"}) as client:
        yield client


def content(request_id="a" * 32):
    return {"request_id": request_id, "name": "Shared guide", "description": "Operational instructions",
            "category": "Runbook", "file": {"name": "guide.txt", "type": "text/plain",
            "data": base64.b64encode(b"Instructions <script>escaped</script>").decode()}}


@pytest.mark.parametrize("filename", ["sheet.xlsx", "sheet.xls", "sheet.csv", "payload.exe", "extensionless", "image.png", "page.html", "movie.avi", "guide.pdf.exe"])
@pytest.mark.asyncio
async def test_knowledge_rejects_unapproved_extensions_on_create_and_replacement(knowledge_client, filename):
    created = await knowledge_client.post("/api/v1/knowledge/content", json=content())
    assert created.status_code == 201
    body = content("b" * 32)
    body["file"] = {"name": filename, "type": "application/pdf", "data": base64.b64encode(b"opaque").decode()}
    rejected = await knowledge_client.post("/api/v1/knowledge/content", json=body)
    assert rejected.status_code == 422
    assert "DOCX, PDF, PPTX, TXT" in rejected.json()["detail"]
    path = f'/api/v1/knowledge/content/{created.json()["id"]}'
    replacement = await knowledge_client.put(path, json={
        "name": "Changed", "description": "Replacement", "category": "SOP",
        "file": body["file"], "expected_revision": 1,
    })
    assert replacement.status_code == 422
    preserved = (await knowledge_client.get("/api/v1/knowledge/content")).json()["items"][0]
    assert preserved["revision"] == 1
    assert preserved["file"]["name"] == "guide.txt"
    assert (await knowledge_client.get(path + "/file")).content == b"Instructions <script>escaped</script>"


@pytest.mark.asyncio
async def test_knowledge_existing_excel_remains_readable_and_metadata_editable(knowledge_client, db_session_factory):
    from sqlalchemy import update
    from app.models.knowledge import KnowledgeContent
    created = await knowledge_client.post("/api/v1/knowledge/content", json=content())
    identifier = int(created.json()["id"])
    async with db_session_factory() as session:
        await session.execute(update(KnowledgeContent).where(KnowledgeContent.id == identifier).values(file_name="existing.xlsx"))
        await session.commit()
    path = f"/api/v1/knowledge/content/{identifier}"
    edited = await knowledge_client.put(path, json={
        "name": "Existing workbook", "description": "Metadata only", "category": "Reference Document",
        "expected_revision": 1, "file": None,
    })
    assert edited.status_code == 200
    assert edited.json()["file"]["name"] == "existing.xlsx"
    assert (await knowledge_client.get(path + "/file")).content == b"Instructions <script>escaped</script>"


@pytest.mark.parametrize("name,mime,raw", [
    ("compressed.pdf", "application/pdf", b"%PDF-1.7 /ObjStm /Encrypt /OpenAction"),
    ("linked.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", b"PK\x03\x04opaque external-linked document"),
    ("instructions.txt", "text/plain", b"\xff\xfeT\x00e\x00x\x00t\x00"),
    ("slides.pptx", "", b"opaque presentation"),
    ("training.mp4", "video/mp4", b"opaque video"),
    ("training.webm", "", b"opaque video"),
    ("training.MOV", "", b"opaque video"),
])
@pytest.mark.asyncio
async def test_knowledge_allowed_files_upload_edit_and_original_bytes(knowledge_client, name, mime, raw):
    body = content()
    body["file"] = {"name": name, "type": mime, "data": base64.b64encode(raw).decode()}
    response = await knowledge_client.post("/api/v1/knowledge/content", json=body)
    assert response.status_code == 201, response.text
    path = f'/api/v1/knowledge/content/{response.json()["id"]}'
    edited = await knowledge_client.put(path, json={
        "name": "Edited", "description": "Preserve bytes", "category": "SOP",
        "file": body["file"], "expected_revision": 1,
    })
    assert edited.status_code == 200, edited.text
    download = await knowledge_client.get(path + "/file")
    assert download.content == raw
    assert download.headers["content-type"] == "application/octet-stream"
    assert download.headers["content-disposition"].startswith("attachment;")
    assert download.headers["x-content-type-options"] == "nosniff"


@pytest.mark.asyncio
async def test_knowledge_rejects_html_upload(knowledge_client):
    body = content()
    raw = b"<script>parent.document.body.innerHTML='changed'</script><p>Preview</p>"
    body["file"] = {"name": "preview.html", "type": "text/html", "data": base64.b64encode(raw).decode()}
    created = await knowledge_client.post("/api/v1/knowledge/content", json=body)
    assert created.status_code == 422, created.text


@pytest.mark.asyncio
async def test_knowledge_preview_returns_safe_text(knowledge_client):
    created = await knowledge_client.post("/api/v1/knowledge/content", json=content())
    path = created.json()["file"]["url"]
    response = await knowledge_client.get(path + "?preview=true")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert response.headers["content-disposition"] == "inline"
    assert response.content == b"Instructions <script>escaped</script>"


@pytest.mark.asyncio
async def test_knowledge_shared_database_file_lifecycle_and_key_enforcement(knowledge_client, api_environment):
    client = knowledge_client
    created = await client.post("/api/v1/knowledge/content", json=content())
    assert created.status_code == 201, created.text
    row = created.json()
    path = f'/api/v1/knowledge/content/{row["id"]}'
    assert row["validatedOn"] is None
    assert (await client.post("/api/v1/knowledge/content", json=content())).json()["id"] == row["id"]
    assert (await client.post("/api/v1/knowledge/content", json={**content(), "name": "Changed retry"})).status_code == 409
    async with AsyncClient(transport=ASGITransport(app=api_environment, client=("127.0.0.1", 1111)),
                           base_url="http://127.0.0.1:8090") as other:
        assert (await other.get("/api/v1/knowledge/content")).json()["items"][0]["name"] == "Shared guide"
        downloaded = await other.get(path + "/file")
        assert downloaded.content == b"Instructions <script>escaped</script>"
        assert downloaded.headers["x-content-type-options"] == "nosniff"
    review = {"reviewer": "Reviewer", "expected_revision": 1}
    assert (await client.post(path + "/validate", json=review, headers={"Authorization": ""})).status_code == 401
    assert (await client.post(path + "/validate", json=review, headers={"Authorization": "Bearer wrong"})).status_code == 401
    validated = await client.post(path + "/validate", json=review, headers={"Authorization": "Bearer test-only-key"})
    assert validated.status_code == 200, validated.text
    assert validated.json()["validatedBy"] == "Reviewer"
    edit = {"name": "Updated guide", "description": "Updated instructions", "category": "SOP", "file": None, "expected_revision": 2}
    updated = await client.put(path, json=edit)
    assert updated.status_code == 200, updated.text
    assert updated.json()["validatedOn"] is None
    assert (await client.put(path, json=edit)).status_code == 409
    assert (await client.get(path + "/file")).content == b"Instructions <script>escaped</script>"
    assert (await client.delete(path + "?expected_revision=3")).status_code == 204
    assert (await client.get("/api/v1/knowledge/content")).json()["total"] == 0
    assert (await client.get(path + "/file")).status_code == 404
    assert (await client.post("/api/v1/knowledge/content", json=content())).status_code == 409


@pytest.mark.asyncio
async def test_knowledge_server_rejects_validation_bypass_invalid_files_and_limits(knowledge_client):
    client = knowledge_client
    body = {**content(), "validatedOn": "2026-10-01", "validatedBy": "Bypass"}
    assert (await client.post("/api/v1/knowledge/content", json=body)).status_code == 422
    body = content()
    body["file"]["name"] = "fake.png"
    body["file"]["type"] = "image/png"
    body["file"]["data"] = base64.b64encode(b"not an image").decode()
    uploaded = await client.post("/api/v1/knowledge/content", json=body)
    assert uploaded.status_code == 422, uploaded.text
    body = content()
    body["file"]["data"] = base64.b64encode(b"x" * (5 * 1024 * 1024 + 1)).decode()
    assert (await client.post("/api/v1/knowledge/content", json=body)).status_code == 422
    assert (await client.post("/api/v1/knowledge/content", content=b"x" * (7 * 1024 * 1024 + 1),
                             headers={"Content-Type": "application/json"})).status_code == 413
    assert (await client.post("/api/v1/knowledge/content", json=content(), headers={"Origin": "http://evil.example"})).status_code == 403


@pytest.mark.asyncio
async def test_knowledge_does_not_inspect_office_content_and_requires_key_configuration(knowledge_client, monkeypatch):
    from app.core.config import settings
    client = knowledge_client
    body = content()
    stream = io.BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("ppt/presentation.xml", "not XML")
    body["file"] = {"name": "slides.pptx", "type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    "data": base64.b64encode(stream.getvalue()).decode()}
    uploaded = await client.post("/api/v1/knowledge/content", json=body)
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["file"]["type"] == "application/octet-stream"
    download = await client.get(f'/api/v1/knowledge/content/{uploaded.json()["id"]}/file')
    assert download.content == stream.getvalue()
    assert download.headers["content-type"] == "application/octet-stream"
    created = (await client.post("/api/v1/knowledge/content", json=content("b" * 32))).json()
    monkeypatch.setattr(settings, "CMDB_INVENTORY_ADMIN_TOKEN", None)
    response = await client.post(f'/api/v1/knowledge/content/{created["id"]}/validate',
                                 json={"reviewer": "Reviewer", "expected_revision": 1})
    assert response.status_code == 503
    assert "Configure CMDB_INVENTORY_ADMIN_TOKEN" in response.json()["detail"]


@pytest.mark.asyncio
async def test_knowledge_database_failure_is_safe_and_explicit(knowledge_client, monkeypatch):
    from sqlalchemy.exc import OperationalError
    from app.services.knowledge_service import KnowledgeService

    async def unavailable(*args):
        raise OperationalError("private statement", {}, RuntimeError("private datastore diagnostic"))

    monkeypatch.setattr(KnowledgeService, "list", unavailable)
    response = await knowledge_client.get("/api/v1/knowledge/content")
    assert response.status_code == 503
    assert "Knowledge datastore unavailable" in response.json()["detail"]
    assert "private" not in response.text


@pytest.mark.asyncio
async def test_knowledge_exact_file_limit_replacement_and_same_cmdb_key(knowledge_client):
    client = knowledge_client
    body = content()
    raw = b"x" * (5 * 1024 * 1024)
    body["file"]["data"] = base64.b64encode(raw).decode()
    response = await client.post("/api/v1/knowledge/content", json=body)
    assert response.status_code == 201, response.text
    row = response.json()
    assert row["file"]["size"] == len(raw)
    path = f'/api/v1/knowledge/content/{row["id"]}'
    assert (await client.get(path + "/file")).content == raw
    edit = {"name": "New file", "description": "Replacement", "category": "Runbook", "expected_revision": 1,
            "file": {"name": "replacement.txt", "type": "text/plain", "data": base64.b64encode(b"replacement").decode()}}
    assert (await client.put(path, json=edit)).status_code == 200
    assert (await client.get(path + "/file")).content == b"replacement"
    assert (await client.get("/api/v1/assets/admin/check", headers={"Authorization": ""})).status_code == 401
    assert (await client.get("/api/v1/assets/admin/check",
                             headers={"Authorization": "Bearer test-only-key"})).status_code == 200


@pytest.mark.parametrize("extension", [".docx", ".pptx"])
@pytest.mark.asyncio
async def test_knowledge_supported_office_formats(knowledge_client, extension):
    from tests.preview_fixtures import office_document
    raw = office_document(extension)
    body = content()
    body["file"] = {"name": "resource" + extension, "type": "application/octet-stream",
                    "data": base64.b64encode(raw).decode()}
    created = await knowledge_client.post("/api/v1/knowledge/content", json=body)
    assert created.status_code == 201, created.text
    downloaded = await knowledge_client.get(f'/api/v1/knowledge/content/{created.json()["id"]}/file')
    assert downloaded.headers["content-type"] == "application/octet-stream"
    assert created.status_code == 201, created.text
    assert (await knowledge_client.get(created.json()["file"]["url"])).content == raw


@pytest.mark.asyncio
async def test_knowledge_edit_delete_require_shared_key(knowledge_client, monkeypatch):
    from app.core.config import settings
    client = knowledge_client
    row = (await client.post("/api/v1/knowledge/content", json=content())).json()
    path = f'/api/v1/knowledge/content/{row["id"]}'
    for token, status in [(None, 503), ("test-only-key", 401)]:
        monkeypatch.setattr(settings, "CMDB_INVENTORY_ADMIN_TOKEN", token)
        assert (await client.put(path, json={"name": "Updated", "description": "Updated", "category": "SOP", "expected_revision": 1},
                                 headers={"Authorization": "Bearer wrong-key"})).status_code == status
        assert (await client.delete(path + "?expected_revision=1", headers={"Authorization": "Bearer wrong-key"})).status_code == status
    assert (await client.get("/api/v1/knowledge/content")).json()["items"][0]["revision"] == 1
