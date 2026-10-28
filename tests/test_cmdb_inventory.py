from io import BytesIO
import asyncio

from openpyxl import Workbook
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints.cmdb_inventory import require_inventory_admin
from app.core.config import settings
from app.core.database import create_sqlite_backup, get_db
from app.main import app
from app.models import Base
from app.repositories.cmdb_inventory_repository import CMDBInventoryRepository
from app.services.cmdb_inventory_service import parse_inventory_workbook


def workbook_bytes(sheets):
    workbook = Workbook()
    first = True
    for title, rows in sheets:
        sheet = workbook.active if first else workbook.create_sheet()
        first = False
        sheet.title = title
        for row in rows:
            sheet.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_network_workbook_preserves_all_columns_and_host_identity():
    content = workbook_bytes([
        ("Network Inventory", [
            ["S.N", "Region", "HostName", "IP Address", "Serial Number"],
            [1, "Philippines", "EDGE-01", "10.0.0.1", 23001017642],
        ])
    ])

    parsed = parse_inventory_workbook(content, "network", "network.xlsx")

    assert parsed.sheet_name == "Network Inventory"
    assert parsed.headers["Network Inventory"] == ["S.N", "Region", "HostName", "IP Address", "Serial Number"]
    assert parsed.records[0]["name"] == "EDGE-01"
    assert parsed.records[0]["data"][4] == {"index": 4, "header": "Serial Number", "value": 23001017642}
    assert parsed.records[0]["source_row"] == 2
    assert parsed.records[0]["source_order"] == 0


def test_server_import_keeps_all_populated_sheets_in_workbook_order():
    content = workbook_bytes([
        ("Coforge Win-Server Working 2026", [
            ["S/N", "Host Name", "IP address", "Operating System", "Status"],
            [1, "APP-01", "10.0.0.2", "Windows Server 2022", "Online"],
        ]),
        ("Decommissioned", [["Computer Name"], ["OLD-01"]]),
        ("Coforge-Linux Working-2026", [["Name", "IP Address", "Status"], ["LINUX-01", "10.0.0.3", "Running"]]),
    ])

    parsed = parse_inventory_workbook(content, "server", "servers.xlsx")

    assert parsed.sheet_name == "Coforge Win-Server Working 2026"
    assert [record["name"] for record in parsed.records] == ["APP-01", "OLD-01", "LINUX-01"]
    assert [record["source_order"] for record in parsed.records] == [0, 1, 2]


def test_telecom_import_finds_header_after_title_and_disambiguates_columns():
    content = workbook_bytes([
        ("WAN Circuit Detail", [
            ["Full WAN Circuit Detail (150 circuits)"],
            [],
            ["S.N", "Region", "Provider", "Bandwidth", "serial no", "Provider"],
            [1, "India", "Singtel", "35 Mbps", "CIRCUIT-01", "Singtel"],
        ])
    ])

    parsed = parse_inventory_workbook(content, "telecom", "telecom.xlsx")

    assert parsed.headers["WAN Circuit Detail"] == ["S.N", "Region", "Provider", "Bandwidth", "serial no", "Provider"]
    assert len(parsed.records) == 1
    assert parsed.records[0]["name"] == "CIRCUIT-01"
    assert parsed.records[0]["source_row"] == 4


def test_inventory_admin_requires_configured_bearer_token(monkeypatch):
    monkeypatch.setattr(settings, "CMDB_INVENTORY_ADMIN_TOKEN", "test-admin-token", raising=False)

    with pytest.raises(Exception) as unauthorized:
        asyncio.run(require_inventory_admin("Bearer wrong-token"))
    assert unauthorized.value.status_code == 401
    assert asyncio.run(require_inventory_admin("Bearer test-admin-token")) == settings.CMDB_INVENTORY_ADMIN_NAME


def test_inventory_repository_validation_edit_and_delete_are_audited():
    async def run():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        content = workbook_bytes([
            ("Network Inventory", [["S.N", "HostName"], [1, "ZZZ-01"], [2, "AAA-02"]])
        ])
        parsed = parse_inventory_workbook(content, "network", "network.xlsx")

        async with sessions() as session:
            repository = CMDBInventoryRepository(session)
            await repository.replace_inventory(parsed, "network.xlsx", "Test Admin", "network")
            page = await repository.list_inventory("network", page=1, page_size=10)
            assert page["total"] == 2
            first = page["items"][0]
            assert first["name"] == "ZZZ-01"
            await repository.validate_field(first["id"], 1, "Test Admin")
            validated = await repository.get_record(first["id"])
            assert validated["field_reviews"]["1"]["validated_by"] == "Test Admin"
            await repository.update_record(first["id"], "EDGE-01-EDITED", first["data"], "Test Admin")
            updated = await repository.get_record(first["id"])
            assert updated["name"] == "EDGE-01-EDITED"
            assert updated["field_reviews"]["1"]["validated_by"] == "Test Admin"
            edited_data = [dict(cell) for cell in first["data"]]
            edited_data[1]["value"] = "EDGE-01-EDITED"
            await repository.update_record(first["id"], "EDGE-01-EDITED", edited_data, "Test Admin")
            updated = await repository.get_record(first["id"])
            assert "1" not in updated["field_reviews"]
            await repository.delete_record(first["id"], "Test Admin")
            remaining = await repository.list_inventory("network", page=1, page_size=10)
            assert remaining["total"] == 1

        await engine.dispose()

    asyncio.run(run())


def test_inventory_api_import_is_admin_protected_and_does_not_enable_telemetry_writes(tmp_path, monkeypatch):
    database_path = tmp_path / "cmdb-inventory-api.db"
    monkeypatch.setattr(settings, "CMDB_INVENTORY_ADMIN_TOKEN", "test-admin-token")

    async def override_database():
        engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
        await engine.dispose()

    app.dependency_overrides[get_db] = override_database
    client = TestClient(app)
    content = workbook_bytes([
        ("Network Inventory", [["S.N", "HostName"], [1, "EDGE-01"]])
    ])
    try:
        denied = client.post(
            "/api/v1/cmdb-inventory/network/import",
            files={"file": ("network.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert denied.status_code == 401

        imported = client.post(
            "/api/v1/cmdb-inventory/network/import",
            headers={"Authorization": "Bearer test-admin-token"},
            files={"file": ("network.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert imported.status_code == 200
        assert imported.json()["imported_count"] == 1
        assert imported.json()["backup_created"] is True
        backups = list((tmp_path / "backups").glob("cmdb-inventory-api-cmdb-network-*.db"))
        assert len(backups) == 1
        summary = client.get("/api/v1/cmdb-inventory/summary")
        assert summary.status_code == 200
        assert summary.json()["network_count"] == 1
        records = client.get("/api/v1/cmdb-inventory/records?inventory_type=network")
        record = records.json()["items"][0]
        field_validation = client.post(
            f"/api/v1/cmdb-inventory/records/{record['id']}/fields/1/validate",
            headers={"Authorization": "Bearer test-admin-token"},
        )
        assert field_validation.status_code == 200
        assert field_validation.json()["field_reviews"]["1"]["header"] == "HostName"
        telemetry_write = client.post("/api/v1/cmdb/cis", json={})
        assert telemetry_write.status_code == 405
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)

def test_sqlite_backup_is_consistent_and_retention_is_bounded(tmp_path):
    import sqlite3
    database = tmp_path / "inventory.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE records(value TEXT)")
        connection.execute("INSERT INTO records VALUES ('kept')")
    for index in range(7):
        backup = create_sqlite_backup(database, f"test-{index}", keep=5)
        assert backup is not None and backup.is_file()
    backups = sorted((tmp_path / "backups").glob("inventory-*.db"))
    assert len(backups) == 5
    with sqlite3.connect(backups[-1]) as connection:
        assert connection.execute("SELECT value FROM records").fetchone()[0] == "kept"


def test_empty_authoritative_database_bootstraps_bundled_inventory(tmp_path, monkeypatch):
    from app.api.v1.endpoints import cmdb_inventory as endpoint

    async def run():
        database = tmp_path / "itom.db"
        server_file = tmp_path / "bootstrap_server_inventory.xlsx"
        network_file = tmp_path / "bootstrap_network_inventory.xlsx"
        server_file.write_bytes(workbook_bytes([("Servers", [["Host Name"], ["SERVER-01"]])]))
        network_file.write_bytes(workbook_bytes([("Network", [["HostName"], ["EDGE-01"], ["EDGE-02"]])]))
        engine = create_async_engine(f"sqlite+aiosqlite:///{database.as_posix()}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(endpoint, "SQLITE_DATABASE_PATH", database.resolve())
        monkeypatch.setattr(endpoint, "BOOTSTRAP_FILES", {"server": server_file, "network": network_file})
        async with sessions() as session:
            await endpoint.ensure_bootstrap_inventory(session)
            summary = await CMDBInventoryRepository(session).summary()
            assert summary["server_count"] == 1
            assert summary["network_count"] == 2
            assert summary["total_records"] == 3
            await endpoint.ensure_bootstrap_inventory(session)
            assert (await CMDBInventoryRepository(session).summary())["total_records"] == 3
        assert list((tmp_path / "backups").glob("itom-cmdb-bootstrap-*.db"))
        await engine.dispose()

    asyncio.run(run())
