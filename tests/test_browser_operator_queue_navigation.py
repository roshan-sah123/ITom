"""Browser integration tests for Overview operator queue navigation and filtering."""

import re
import pytest
from playwright.sync_api import sync_playwright, expect


PORTAL_URL = "http://localhost:8080/index.html"


@pytest.fixture(scope="module")
def browser_context():
    """Launch headless browser using system Edge or Chromium."""
    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
    except Exception:
        browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    yield context
    context.close()
    browser.close()
    playwright.stop()


def test_operator_queue_solarwinds_nodes_review(browser_context):
    """Clicking 'SolarWinds nodes need review' -> 'View' navigates to Infrastructure Servers,
    applies Health Tier = Low/Critical filter, displays active filter banner, and refreshes table."""
    page = browser_context.new_page()
    page.goto(PORTAL_URL, wait_until="domcontentloaded")

    # Verify overview loaded
    expect(page.locator("#view-home")).to_be_visible()
    expect(page.locator("#attentionList")).to_be_visible()

    # Find the SolarWinds operator queue button
    sw_card = page.locator("#attentionList button.attention-item:has-text('SolarWinds nodes need review')")
    expect(sw_card).to_be_visible(timeout=15000)

    # Extract dynamic count from operator queue card text
    card_text = sw_card.text_content() or ""
    match = re.search(r"([\d,]+)\s+SolarWinds nodes need review", card_text)
    assert match, f"Expected node count in card text: {card_text}"
    expected_count = match.group(1)

    # Click the 'View' link/button
    sw_card.locator("i:has-text('View')").click()

    # 1. Navigate to Infrastructure > Servers view
    infra_view = page.locator("#view-infrastructure")
    expect(infra_view).to_have_class(re.compile(r"\bactive\b"))
    servers_subview = page.locator("#subview-servers")
    expect(servers_subview).to_be_visible()
    servers_tab = page.locator(".category-card-tab[data-subtab='servers']")
    expect(servers_tab).to_have_class(re.compile(r"\bactive\b"))

    # 2. Automatically apply filter Health Tier = Low/Critical
    health_select = page.locator("#swFilterHealth")
    expect(health_select).to_have_value("Low")

    # 3. Show active filter banner
    filter_banner = page.locator("#swActiveFilterBanner")
    expect(filter_banner).to_be_visible()
    filter_label = page.locator("#swActiveFilterLabel")
    expect(filter_label).to_contain_text("Health Tier")
    expect(filter_label).to_contain_text("Low")

    # 4. Refresh table using filtered API request & populate rows
    table_body = page.locator("#swServerTableBody")
    expect(table_body.locator("tr")).not_to_have_count(0, timeout=10000)

    # First row should show Low health tier
    first_health_pill = table_body.locator("tr").first.locator(".status-pill")
    expect(first_health_pill).to_contain_text("Low")

    # 5. Ensure displayed result count matches filtered records
    record_count = page.locator("#swRecordCount")
    expect(record_count).to_contain_text(f"of {expected_count} Server Nodes")

    # Verify Clear Filter restores full list
    clear_btn = page.locator("#swClearActiveFilterBtn")
    clear_btn.click()
    expect(filter_banner).to_be_hidden()
    expect(health_select).to_have_value("")
    expect(record_count).not_to_contain_text(f"of {expected_count} Server Nodes")
    expect(record_count).to_contain_text("Server Nodes")

    page.close()


def test_operator_queue_endpoints_noncompliant(browser_context):
    """Clicking 'Endpoints are noncompliant' -> 'View' navigates to Endpoints,
    selects Compliance Status = Noncompliant, displays active filter banner, and refreshes table."""
    page = browser_context.new_page()
    page.goto(PORTAL_URL, wait_until="domcontentloaded")

    # Verify overview loaded
    expect(page.locator("#view-home")).to_be_visible()
    expect(page.locator("#attentionList")).to_be_visible()

    # Find the Endpoints operator queue button
    ep_card = page.locator("#attentionList button.attention-item:has-text('endpoints are noncompliant')")
    expect(ep_card).to_be_visible(timeout=15000)

    # Extract dynamic count from operator queue card text
    card_text = ep_card.text_content() or ""
    match = re.search(r"([\d,]+)\s+endpoints are noncompliant", card_text)
    assert match, f"Expected endpoint count in card text: {card_text}"
    expected_count = match.group(1)

    # Click the 'View' link/button
    ep_card.locator("i:has-text('View')").click()

    # 1. Navigate to Endpoints view
    ep_view = page.locator("#view-endpoints")
    expect(ep_view).to_have_class(re.compile(r"\bactive\b"))

    # 2. Automatically select Compliance Status = Noncompliant
    status_select = page.locator("#epFilterStatus")
    expect(status_select).to_have_value("Noncompliant")

    # 3. Show active filter banner
    filter_banner = page.locator("#epActiveFilterBanner")
    expect(filter_banner).to_be_visible()
    filter_label = page.locator("#epActiveFilterLabel")
    expect(filter_label).to_contain_text("Noncompliant")

    # 4. Refresh table using filtered API request & populate rows
    table_body = page.locator("#epDeviceTableBody")
    expect(table_body.locator("tr")).not_to_have_count(0, timeout=10000)

    # First row should show Noncompliant status
    first_status_pill = table_body.locator("tr").first.locator(".status-pill")
    expect(first_status_pill).to_contain_text("Noncompliant")

    # 5. Ensure result count matches filtered records
    record_count = page.locator("#epRecordCount")
    expect(record_count).to_contain_text(f"of {expected_count} Managed Devices")

    # Verify Clear Filter restores full list
    clear_btn = page.locator("#epClearActiveFilterBtn")
    clear_btn.click()
    expect(filter_banner).to_be_hidden()
    expect(status_select).to_have_value("")
    expect(record_count).not_to_contain_text(f"of {expected_count} Managed Devices")
    expect(record_count).to_contain_text("Managed Devices")

    page.close()
