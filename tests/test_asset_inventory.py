from datetime import datetime

import openpyxl
import pytest


def write_workbook(path, rows, sheet_name="Inventory"):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = sheet_name
    for row in rows:
        sheet.append(row)
    workbook.save(path)
    workbook.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("category", ["server", "network", "telecom"])
async def test_asset_expanded_page_sizes_preserve_pagination(api_environment, tmp_path, category):
    from httpx import ASGITransport, AsyncClient
    from app.api.v1.endpoints.assets import get_asset_inventory_service
    from app.services.asset_inventory_service import AssetInventoryService

    write_workbook(tmp_path / f"{category}.xlsx",
                   [["HOST NAME", "Site"]] + [[f"asset-{index:03}", "Delhi"] for index in range(205)])
    api_environment.dependency_overrides[get_asset_inventory_service] = lambda: AssetInventoryService(tmp_path)
    async with AsyncClient(transport=ASGITransport(app=api_environment, client=("127.0.0.1", 1234)),
                           base_url="http://127.0.0.1:8080") as client:
        for route in ["records", "inventory"]:
            for size in [100, 150, 200]:
                first = await client.get(f"/api/v1/assets/{route}/{category}?page_size={size}")
                assert first.status_code == 200, first.text
                assert len(first.json()["items"]) == size
                assert first.json()["total"] == 205
                second = await client.get(f"/api/v1/assets/{route}/{category}?page_size={size}&page=2")
                assert second.status_code == 200
                assert len(second.json()["items"]) == min(size, 205 - size)
            assert (await client.get(f"/api/v1/assets/{route}/{category}?page_size=201")).status_code == 422


def test_asset_inventory_reads_the_best_header_row_and_paginates_search(tmp_path):
    from app.services.asset_inventory_service import AssetInventoryService

    write_workbook(
        tmp_path / "telecom.xlsx",
        [
            ["WAN Circuit Detail"],
            [],
            ["Circuit ID", "Site", "Provider", "Last reviewed"],
            ["C-001", "Bengaluru", "Carrier A", datetime(2026, 10, 20)],
            ["C-002", "Pune", "Carrier B", datetime(2026, 10, 21)],
        ],
        sheet_name="WAN Circuit Detail",
    )
    service = AssetInventoryService(tmp_path)

    result = service.list_inventory(
        "telecom", page=1, page_size=10, search="carrier b"
    )

    assert result["columns"] == ["Circuit ID", "Site", "Provider", "Last reviewed"]
    assert result["items"] == [
        {
            "Circuit ID": "C-002",
            "Site": "Pune",
            "Provider": "Carrier B",
            "Last reviewed": "2026-10-21T00:00:00",
        }
    ]
    assert result["total"] == 1
    assert result["total_pages"] == 1


def test_asset_inventory_summary_distinguishes_missing_workbooks(tmp_path):
    from app.services.asset_inventory_service import AssetInventoryService

    write_workbook(
        tmp_path / "server.xlsx",
        [["S.N", "HOST NAME"], [1, "srv-01"], [2, "srv-02"]],
    )
    service = AssetInventoryService(tmp_path)

    summary = service.summary()
    by_category = {item["category"]: item for item in summary["items"]}

    assert summary["data_available"] is True
    assert by_category["server"]["data_available"] is True
    assert by_category["server"]["total"] == 2
    assert by_category["network"]["data_available"] is False
    assert by_category["network"]["total"] is None


@pytest.mark.asyncio
async def test_asset_inventory_api_serves_configured_records_and_reports_missing_files(
    api_environment, tmp_path
):
    from httpx import ASGITransport, AsyncClient
    from app.api.v1.endpoints.assets import get_asset_inventory_service
    from app.services.asset_inventory_service import AssetInventoryService

    write_workbook(
        tmp_path / "network.xlsx",
        [["S.N", "HOST NAME"], [1, "switch-01"], [2, "router-02"]],
    )
    api_environment.dependency_overrides[get_asset_inventory_service] = (
        lambda: AssetInventoryService(tmp_path)
    )

    async with AsyncClient(transport=ASGITransport(app=api_environment, client=("127.0.0.1", 1234)),
                           base_url="http://127.0.0.1:8080") as api_client:
        response = await api_client.get(
            "/api/v1/assets/inventory/network?page=1&page_size=10&search=switch"
        )
        missing_response = await api_client.get("/api/v1/assets/inventory/server")
        invalid_page_size = await api_client.get(
            "/api/v1/assets/inventory/network?page_size=12"
        )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["HOST NAME"] == "switch-01"
    assert missing_response.status_code == 503
    assert missing_response.json()["data_available"] is False
    assert invalid_page_size.status_code == 422
