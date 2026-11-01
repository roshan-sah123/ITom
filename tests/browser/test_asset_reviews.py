from pathlib import Path

import openpyxl
import pytest
from tests.browser.dialog_assertions import assert_centered

expect = pytest.importorskip("playwright.sync_api").expect
pytestmark = pytest.mark.browser


@pytest.fixture
def asset_portal_url(api_environment, tmp_path, request):
    from app.api.v1.endpoints.assets import get_asset_inventory_service
    from app.services.asset_inventory_service import AssetInventoryService
    for category in ["server", "network", "telecom"]:
        book = openpyxl.Workbook()
        book.active.append(["HOST NAME", "Site"])
        book.active.append([f"{category}-01", "Delhi"])
        book.save(tmp_path / f"{category}.xlsx")
        book.close()
    api_environment.dependency_overrides[get_asset_inventory_service] = lambda: AssetInventoryService(tmp_path)
    return request.getfixturevalue("module_portal_url")


def test_cmdb_categories_row_cell_reviews_edit_export_add_delete(asset_portal_url, browser_context):
    page = browser_context.new_page()
    page.goto(asset_portal_url)
    page.get_by_role("button", name="Assets Analytics", exact=True).click()
    expect(page.locator(".asset-summary-grid > button")).to_have_count(3)
    expect(page.locator(".asset-cmdb-heading")).to_have_count(0)
    expect(page.locator(".asset-readonly-badge")).to_have_count(0)
    expect(page.get_by_text("CMDB SNAPSHOT", exact=True)).to_have_count(0)
    assert page.get_by_role("button", name="Import / change inventory file").count() == 0
    for label, category in [("Servers", "server"), ("Network devices", "network"), ("Telecom", "telecom")]:
        page.get_by_role("button", name=f"Open {label} inventory", exact=True).click()
        inventory = page.get_by_role("dialog", name=label, exact=True)
        expect(inventory.locator("tbody tr")).to_have_count(1)
        expect(inventory.locator(".asset-cell-button small")).to_have_count(0)
        assert_centered(inventory)
        inventory.get_by_role("button", name="Edit mode", exact=True).click()
        unlock = page.get_by_role("dialog", name="Enable inventory editing")
        assert_centered(unlock)
        unlock.get_by_label("CMDB admin key", exact=True).fill("wrong-key")
        unlock.get_by_role("button", name="Enable editing", exact=True).click()
        expect(unlock.get_by_role("alert")).to_contain_text("valid CMDB admin key")
        unlock.get_by_label("CMDB admin key", exact=True).fill("isolated-review-key")
        unlock.get_by_role("button", name="Enable editing", exact=True).click()
        inventory.get_by_role("button", name=f"Open Site for {category}-01", exact=True).click()
        cell = page.get_by_role("dialog", name="Inventory cell", exact=True)
        assert_centered(cell)
        cell.get_by_label("Operator / reviewer name *", exact=True).fill("Cell reviewer")
        cell.get_by_role("button", name="Validate field", exact=True).click()
        expect(inventory.get_by_role("button", name=f"Open Site for {category}-01", exact=True)).to_have_text("Delhi")
        inventory.get_by_role("button", name=f"Open Site for {category}-01", exact=True).click()
        expect(cell).to_contain_text("Reviewed by Cell reviewer")
        cell.get_by_role("button", name="Close", exact=True).click()
        inventory.get_by_role("button", name="Validate", exact=True).click()
        review = page.get_by_role("dialog", name="Validate inventory row")
        assert_centered(review)
        review.get_by_label("Operator / reviewer name *", exact=True).fill("Row reviewer")
        review.get_by_role("button", name="Validate", exact=True).click()
        expect(inventory.get_by_role("button", name="Validated", exact=True)).to_be_disabled()
        inventory.get_by_role("button", name="Edit", exact=True).click()
        edit = page.get_by_role("dialog", name="Edit inventory row")
        assert_centered(edit)
        edit.get_by_label("Site", exact=True).fill("Pune")
        edit.get_by_label("Operator / reviewer name *", exact=True).fill("Editor")
        edit.get_by_role("button", name="Save changes", exact=True).click()
        expect(inventory.locator("tbody tr")).to_contain_text("Pune")
        expect(inventory.get_by_role("button", name="Validate", exact=True)).to_be_enabled()
        with page.expect_download() as download:
            inventory.get_by_role("button", name="Export CSV", exact=True).click()
        assert "Pune" in Path(download.value.path()).read_text(encoding="utf-8-sig")
        inventory.get_by_role("button", name="+ Add data", exact=True).click()
        add = page.get_by_role("dialog", name="Add inventory row")
        assert_centered(add)
        add.get_by_label("Record name *", exact=True).fill(f"{category}-02")
        add.get_by_label("HOST NAME", exact=True).fill(f"{category}-02")
        add.get_by_label("Site", exact=True).fill("Noida")
        add.get_by_label("Operator / reviewer name *", exact=True).fill("Editor")
        add.get_by_role("button", name="Save changes", exact=True).click()
        expect(inventory.locator("tbody tr")).to_have_count(2)
        inventory.locator("tbody tr").filter(has_text=f"{category}-02").get_by_role("button", name="Delete", exact=True).click()
        deleted = page.get_by_role("dialog", name="Delete inventory row")
        assert_centered(deleted)
        deleted.get_by_label("Operator / reviewer name *", exact=True).fill("Editor")
        deleted.get_by_role("button", name="Delete", exact=True).click()
        expect(inventory.locator("tbody tr")).to_have_count(1)
        inventory.get_by_role("button", name=f"Close {label} inventory", exact=True).click()
    assert page.url == asset_portal_url
    page.close()
