"""The local portal and its API are served from one ASGI listener."""

from fastapi.testclient import TestClient

from app.main import app
from app.core import database
from app.core.config import settings


def test_fastapi_serves_portal_and_assets_from_root():
    client = TestClient(app)
    response = client.get("/")
    asset = client.get("/js/api.js")
    client.close()

    assert response.status_code == 200
    assert "Coforge ITOM Operations Portal" in response.text
    assert asset.status_code == 200
    assert "window.ITOM_API_BASE || '/api/v1'" in asset.text


def test_readiness_and_dashboard_are_available_on_same_origin():
    client = TestClient(app)
    dashboard = client.get("/")
    readiness = client.get("/healthz")
    client.close()

    assert dashboard.status_code == 200
    assert readiness.status_code == 200
    assert readiness.json()["status"] == "ok"


def test_sqlite_fallback_uses_configured_database_path(monkeypatch):
    from pathlib import Path

    database_path = Path("C:/main-project/data/itom.db")
    monkeypatch.setattr(settings, "SQLITE_DB_PATH", str(database_path))

    fallback_url = database._sqlite_fallback_url("C:/worktree")

    assert fallback_url == f"sqlite+aiosqlite:///{database_path.as_posix()}"
