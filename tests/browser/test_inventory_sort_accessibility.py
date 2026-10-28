"""Inventory sorting exposes its current direction to assistive technology."""
import pytest

expect = pytest.importorskip("playwright.sync_api").expect
pytestmark = pytest.mark.browser


def test_inventory_sort_direction_is_announced(revamp_portal_url, browser_context):
    page = browser_context.new_page()
    page.goto(revamp_portal_url)
    page.get_by_role("button", name="Operations Analytics", exact=True).click()
    page.get_by_role("button", name="View Classified servers", exact=True).click()
    header = page.locator(".inventory-panel th").first
    expect(header).to_have_attribute("aria-sort", "ascending")
    header.get_by_role("button").click()
    expect(header).to_have_attribute("aria-sort", "descending")
    page.close()
