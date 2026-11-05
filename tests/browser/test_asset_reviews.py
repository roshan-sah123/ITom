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


@pytest.mark.parametrize("fullscreen", [False, True])
@pytest.mark.parametrize("viewport", [{"width": 1440, "height": 900}, {"width": 390, "height": 844}])
def test_all_inventory_column_headers_stay_visible_while_scrolling(asset_portal_url, browser_context, fullscreen, viewport):
    assert browser_context.request.get(asset_portal_url + "api/v1/assets/summary").ok
    page = browser_context.new_page()
    page.set_viewport_size(viewport)
    page.goto(asset_portal_url)
    page.get_by_role("button", name="Assets Analytics", exact=True).click()
    for label in ["Servers", "Network devices", "Telecom"]:
        page.get_by_role("button", name=f"Open {label} inventory", exact=True).click()
        dialog = page.get_by_role("dialog", name=label, exact=True)
        expect(dialog.locator("tbody tr")).to_have_count(1)
        if fullscreen:
            dialog.get_by_role("button", name=f"Full screen {label} inventory", exact=True).click()
        # Duplicate only fixture rows in the browser to exercise overflow without changing records.
        dialog.locator("tbody").evaluate("""body => {
          const row = body.firstElementChild;
          for (let i=0; i<70; i++) body.append(row.cloneNode(true));
        }""")
        header = dialog.locator("thead th").first
        before = header.bounding_box()
        scroller = dialog.locator(".asset-table-wrap")
        scroller.evaluate("element => { element.scrollTop = 500; }")
        page.wait_for_function("document.querySelector('.asset-table-wrap').scrollTop > 100")
        after = header.bounding_box()
        assert abs(before["y"] - after["y"]) <= 2
        assert header.evaluate("element => getComputedStyle(element).position") == "sticky"
        dialog.get_by_role("button", name=f"Close {label} inventory", exact=True).click()
    page.close()


@pytest.mark.parametrize("viewport", [{"width": 1440, "height": 900}, {"width": 390, "height": 844}])
def test_asset_dialog_corner_controls_fullscreen_and_navigation_order(asset_portal_url, browser_context, viewport):
    page = browser_context.new_page()
    page.set_viewport_size(viewport)
    page.goto(asset_portal_url)
    navigation = page.get_by_role("navigation", name="Primary navigation")
    labels = navigation.get_by_role("button").all_text_contents()
    assert next(i for i, label in enumerate(labels) if "Vendor Management" in label) < next(
        i for i, label in enumerate(labels) if "Automations" in label)
    page.get_by_role("button", name="Assets Analytics", exact=True).click()
    for label in ["Servers", "Network devices", "Telecom"]:
        page.get_by_role("button", name=f"Open {label} inventory", exact=True).click()
        inventory = page.get_by_role("dialog", name=label, exact=True)
        expect(inventory.locator("tbody tr")).to_have_count(1)
        expect(inventory.get_by_text("Workbook sources remain unchanged.", exact=False)).to_have_count(0)
        close = inventory.get_by_role("button", name=f"Close {label} inventory", exact=True)
        expand = inventory.get_by_role("button", name=f"Full screen {label} inventory", exact=True)
        expect(close).to_be_visible()
        expect(expand).to_be_visible()
        original = inventory.bounding_box()
        corner = close.bounding_box()
        assert 0 <= original["x"] + original["width"] - corner["x"] - corner["width"] <= 25
        assert 0 <= corner["y"] - original["y"] <= 25
        inventory.get_by_role("searchbox").fill("Delhi")
        expand.click()
        restore = inventory.get_by_role("button", name=f"Restore {label} inventory size", exact=True)
        expect(restore).to_have_attribute("aria-pressed", "true")
        fullscreen = inventory.bounding_box()
        assert abs(fullscreen["width"] - viewport["width"]) <= 2
        assert abs(fullscreen["height"] - viewport["height"]) <= 2
        expect(inventory.get_by_role("searchbox")).to_have_value("Delhi")
        expect(inventory.locator("tbody tr")).to_have_count(1)
        inventory.get_by_role("button", name="Edit mode", exact=True).click()
        unlock = page.get_by_role("dialog", name="Enable inventory editing")
        expect(unlock).to_be_visible()
        assert_centered(unlock)
        unlock.get_by_role("button", name="Close Enable inventory editing", exact=True).click()
        restore.click()
        expect(expand).to_have_attribute("aria-pressed", "false")
        assert abs(inventory.bounding_box()["width"] - original["width"]) <= 2
        close.click()
        expect(inventory).to_have_count(0)
        page.get_by_role("button", name=f"Open {label} inventory", exact=True).click()
        expect(page.get_by_role("button", name=f"Full screen {label} inventory")).to_have_attribute("aria-pressed", "false")
        page.get_by_role("button", name=f"Full screen {label} inventory").click()
        page.keyboard.press("Escape")
        expect(inventory).to_have_count(0)
    page.close()
