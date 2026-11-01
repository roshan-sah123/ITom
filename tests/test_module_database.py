"""Prove module isolation without connecting to the deployed databases."""
import base64
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import openpyxl
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import inspect, text

from app.core.config import Settings
from app.core import database
from app.models.base import Base

ROOT = Path(__file__).resolve().parents[1]
MODULE_TABLES = {
    "vendor_submissions", "knowledge_content", "asset_inventory_batches",
    "asset_inventory_records", "asset_inventory_audit",
}


def migrate_modules(primary, secondary, *arguments):
    environment = dict(
        os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{primary.as_posix()}",
        DATABASE_URL_2=f"sqlite+aiosqlite:///{secondary.as_posix()}",
    )
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic-modules.ini", *arguments],
        cwd=ROOT, env=environment, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_module_migration_is_separate_idempotent_and_reversible(tmp_path):
    primary, secondary = tmp_path / "primary.db", tmp_path / "nested" / "modules.db"
    with sqlite3.connect(primary) as connection:
        connection.execute("CREATE TABLE preserved (value TEXT)")
        connection.execute("INSERT INTO preserved VALUES ('unchanged')")
    before = primary.read_bytes()
    migrate_modules(primary, secondary, "upgrade", "head")
    with sqlite3.connect(secondary) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert tables == MODULE_TABLES | {"module_alembic_version"}
        for name in MODULE_TABLES:
            columns = {row[1] for row in connection.execute(f'PRAGMA table_info("{name}")')}
            assert columns == set(Base.metadata.tables[name].columns.keys())
    migrate_modules(primary, secondary, "upgrade", "head")
    migrate_modules(primary, secondary, "downgrade", "base")
    with sqlite3.connect(secondary) as connection:
        assert not connection.execute("SELECT name FROM sqlite_master WHERE name='knowledge_content'").fetchall()
    assert primary.read_bytes() == before


def test_secondary_defaults_to_its_own_file_and_rejects_shared_or_invalid_urls(monkeypatch):
    monkeypatch.delenv("DATABASE_URL_2")
    settings = Settings(_env_file=None, DATABASE_URL="postgresql://operator@localhost/telemetry")
    assert settings.DATABASE_URL_2 == "sqlite+aiosqlite:///./data/modules.db"
    assert settings.async_database_url.startswith("postgresql+asyncpg://")
    assert settings.module_database_url.endswith("/data/modules.db")
    for secondary in ("", "postgresql://operator@localhost/telemetry", "sqlite+aiosqlite:///./data/itom.db"):
        with pytest.raises(ValueError):
            Settings(_env_file=None, DATABASE_URL="sqlite+aiosqlite:///./data/itom.db", DATABASE_URL_2=secondary)
    alias = Settings(_env_file=None, DATABASE_URL="sqlite+aiosqlite:///./data/telemetry.db",
                     DATABASE_URL_2="sqlite:///./data/itom.db", SQLITE_DB_PATH="./data/other.db")
    assert alias.module_database_url.endswith("/data/itom.db")
    Settings(_env_file=None, DATABASE_URL="sqlite+aiosqlite:///./data/telemetry.db?timeout=30")


def test_module_migration_does_not_connect_to_postgres_primary(tmp_path):
    secondary = tmp_path / "modules.db"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic-modules.ini", "upgrade", "head"],
        cwd=ROOT, env=dict(os.environ, DATABASE_URL="postgresql+asyncpg://operator@127.0.0.1:1/telemetry",
                          DATABASE_URL_2=f"sqlite+aiosqlite:///{secondary.as_posix()}"),
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert secondary.exists()


@pytest.mark.asyncio
async def test_primary_bootstrap_excludes_module_tables(tmp_path):
    primary = database.create_engine_for_url(f"sqlite+aiosqlite:///{(tmp_path / 'primary.db').as_posix()}")
    try:
        await database.create_db_and_tables(primary)
        async with primary.connect() as connection:
            tables = set(await connection.run_sync(lambda sync: inspect(sync).get_table_names()))
        assert "configuration_items" in tables
        assert not tables & MODULE_TABLES
    finally:
        await primary.dispose()


@pytest.mark.asyncio
async def test_module_dependency_writes_only_secondary_and_survives_reconnect(api_environment, tmp_path, monkeypatch):
    from app.api.v1.endpoints.assets import get_asset_inventory_service
    from app.services.asset_inventory_service import AssetInventoryService
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.core.config import settings

    primary, secondary = tmp_path / "untouched.db", tmp_path / "modules.db"
    migrate_modules(primary, secondary, "upgrade", "head")
    secondary_engine = database.create_engine_for_url(f"sqlite+aiosqlite:///{secondary.as_posix()}")
    monkeypatch.setattr(database, "ModuleSessionLocal", async_sessionmaker(secondary_engine, expire_on_commit=False))
    monkeypatch.setattr(settings, "CMDB_INVENTORY_ADMIN_TOKEN", "isolated-module-key")
    api_environment.dependency_overrides.pop(database.get_module_db, None)
    for category in ("server", "network", "telecom"):
        workbook = openpyxl.Workbook()
        workbook.active.append(["HOST NAME", "Site"])
        workbook.active.append([f"isolated-{category}", "Site"])
        workbook.save(tmp_path / f"{category}.xlsx")
        workbook.close()
    from tests.factories import make_ci
    async with database.AsyncSessionLocal() as session:
        session.add(make_ci("INTUNE", "preserved-telemetry", "Compliant", "High"))
        await session.commit()
    api_environment.dependency_overrides[get_asset_inventory_service] = lambda: AssetInventoryService(tmp_path)
    transport = ASGITransport(app=api_environment, client=("127.0.0.1", 1234))
    try:
        async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8090",
                               headers={"Origin": "http://127.0.0.1:8090", "Authorization": "Bearer isolated-module-key"}) as client:
            telemetry_before = (await client.get("/api/v1/cmdb/cis")).json()
            vendor = await client.post("/api/v1/vendors/submissions", json={
                "request_id": "a" * 32, "vendor": "Partner", "method": "Portal",
                "steps": [{"what_to_do": "Open", "how_to_do": "Sign in", "image": None}], "sop": None,
            })
            assert vendor.status_code == 201, vendor.text
            knowledge = await client.post("/api/v1/knowledge/content", json={
                "request_id": "b" * 32, "name": "Shared guide", "description": "Instructions", "category": "Runbook",
                "file": {"name": "guide.txt", "type": "text/plain", "data": base64.b64encode(b"Shared bytes").decode()},
            })
            assert knowledge.status_code == 201, knowledge.text
            vendor_path = f'/api/v1/vendors/submissions/{vendor.json()["id"]}'
            assert (await client.post(vendor_path + "/validate", json={"reviewer": "Reviewer", "expected_revision": 1})).status_code == 200
            edited_vendor = await client.put(vendor_path, json={
                "request_id": "a" * 32, "vendor": "Updated partner", "method": "Portal",
                "steps": [{"what_to_do": "Open", "how_to_do": "Sign in", "image": None}], "sop": None, "expected_revision": 2,
            })
            assert edited_vendor.status_code == 200, edited_vendor.text
            knowledge_path = f'/api/v1/knowledge/content/{knowledge.json()["id"]}'
            assert (await client.post(knowledge_path + "/validate", json={"reviewer": "Reviewer", "expected_revision": 1})).status_code == 200
            edited_knowledge = await client.put(knowledge_path, json={
                "name": "Updated guide", "description": "Instructions", "category": "Runbook",
                "file": None, "expected_revision": 2,
            })
            assert edited_knowledge.status_code == 200, edited_knowledge.text
            inventory_paths = []
            for category in ("server", "network", "telecom"):
                inventory = await client.get(f"/api/v1/assets/records/{category}")
                assert inventory.status_code == 200, inventory.text
                assert inventory.json()["total"] == 1
                row = inventory.json()["items"][0]
                path = f'/api/v1/assets/records/{category}/{row["id"]}'
                inventory_paths.append(path)
                assert (await client.post(path + "/validate", json={"actor": "Reviewer", "expected_revision": 1})).status_code == 200
                updated = await client.put(path, json={
                    "actor": "Editor", "expected_revision": 2, "name": row["name"], "data": row["data"],
                })
                assert updated.status_code == 200, updated.text
            assert (await client.get("/ready/modules")).status_code == 200
            assert (await client.get("/api/v1/cmdb/cis")).json() == telemetry_before
        # New connections/users still see the same persisted data.
        await secondary_engine.dispose()
        async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8090") as other:
            assert (await other.get("/api/v1/vendors/submissions")).json()["total"] == 1
            assert (await other.get("/api/v1/vendors/submissions")).json()["items"][0]["vendor"] == "Updated partner"
            assert (await other.get("/api/v1/knowledge/content")).json()["items"][0]["name"] == "Updated guide"
            assert (await other.get(f'/api/v1/knowledge/content/{knowledge.json()["id"]}/file')).content == b"Shared bytes"
            for category in ("server", "network", "telecom"):
                row = (await other.get(f"/api/v1/assets/records/{category}")).json()["items"][0]
                assert row["revision"] == 3 and row["validated_by"] == "Reviewer"
            other.headers.update({"Origin": "http://127.0.0.1:8090", "Authorization": "Bearer isolated-module-key"})
            assert (await other.delete(vendor_path + "?expected_revision=3")).status_code == 204
            assert (await other.delete(knowledge_path + "?expected_revision=3")).status_code == 204
            for path in inventory_paths:
                assert (await other.request("DELETE", path, json={"actor": "Editor", "expected_revision": 3})).status_code == 204
        async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8090") as reader:
            assert (await reader.get("/api/v1/vendors/submissions")).json()["total"] == 0
            assert (await reader.get("/api/v1/knowledge/content")).json()["total"] == 0
            for category in ("server", "network", "telecom"):
                assert (await reader.get(f"/api/v1/assets/records/{category}")).json()["total"] == 0
            assert (await reader.get("/api/v1/cmdb/cis")).json() == telemetry_before
        with sqlite3.connect(secondary) as connection:
            assert connection.execute("SELECT is_deleted FROM vendor_submissions").fetchone()[0] == 1
            assert connection.execute("SELECT is_deleted,file_data FROM knowledge_content").fetchone() == (1, b"")
            assert connection.execute("SELECT COUNT(*) FROM asset_inventory_records WHERE is_deleted=1").fetchone()[0] == 3
        async with database.AsyncSessionLocal() as session:
            for name in MODULE_TABLES:
                assert (await session.execute(text(f'SELECT COUNT(*) FROM "{name}"'))).scalar_one() == 0
    finally:
        await secondary_engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["unmigrated", "revision_mismatch", "missing_table", "unreachable"])
async def test_unmigrated_secondary_fails_explicitly_without_primary_fallback(api_environment, tmp_path, monkeypatch, failure):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    path = tmp_path / "empty.db"
    if failure == "unreachable":
        path = tmp_path / "missing-directory" / "empty.db"
    elif failure in {"revision_mismatch", "missing_table"}:
        migrate_modules(tmp_path / "primary.db", path, "upgrade", "head")
        with sqlite3.connect(path) as connection:
            if failure == "revision_mismatch":
                connection.execute("UPDATE module_alembic_version SET version_num='wrong'")
            else:
                connection.execute("DROP TABLE knowledge_content")
    secondary = database.create_engine_for_url(f"sqlite+aiosqlite:///{path.as_posix()}")
    monkeypatch.setattr(database, "ModuleSessionLocal", async_sessionmaker(secondary))
    api_environment.dependency_overrides.pop(database.get_module_db, None)
    try:
        async with AsyncClient(transport=ASGITransport(app=api_environment, client=("127.0.0.1", 1234)),
                               base_url="http://127.0.0.1:8090") as client:
            for path in ("/ready/modules", "/api/v1/vendors/submissions", "/api/v1/knowledge/content", "/api/v1/assets/summary"):
                response = await client.get(path)
                assert response.status_code == 503, response.text
                assert "Module datastore unavailable" in response.text
                assert str(tmp_path) not in response.text
            assert (await client.get("/ready")).status_code == 200
    finally:
        await secondary.dispose()


@pytest.mark.asyncio
async def test_module_readiness_rejects_read_only_storage(api_environment, tmp_path, monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    path = tmp_path / "readonly.db"
    migrate_modules(tmp_path / "primary.db", path, "upgrade", "head")
    writable = database.create_engine_for_url(f"sqlite+aiosqlite:///{path.as_posix()}")
    async with writable.connect() as connection:
        await connection.execute(text("SELECT 1"))
    await writable.dispose()
    readonly = database.create_engine_for_url(f"sqlite+aiosqlite:///file:{path.as_posix()}?mode=ro&uri=true")
    monkeypatch.setattr(database, "ModuleSessionLocal", async_sessionmaker(readonly))
    api_environment.dependency_overrides.pop(database.get_module_db, None)
    try:
        async with AsyncClient(transport=ASGITransport(app=api_environment, client=("127.0.0.1", 1234)),
                               base_url="http://127.0.0.1:8090") as client:
            assert (await client.get("/api/v1/knowledge/content")).status_code == 200
            assert (await client.get("/ready/modules")).status_code == 503
    finally:
        await readonly.dispose()
