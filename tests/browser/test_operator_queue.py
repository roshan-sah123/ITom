"""Browser integration tests for Overview operator queue navigation and filtering."""

import re
from urllib.parse import urljoin
import pytest
playwright_api = pytest.importorskip("playwright.sync_api")
sync_playwright, expect = playwright_api.sync_playwright, playwright_api.expect
pytestmark = pytest.mark.browser





@pytest.fixture
def browser_context():
    """Launch headless browser using system Edge or Chromium."""
    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
    except Exception:
        browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    # External font CSS is unrelated to these journeys and can block DOMContentLoaded
    # on corporate networks. Keep actual application/API and Chart.js execution.
    context.route('https://fonts.googleapis.com/**',lambda route: route.abort())
    context.route('https://fonts.gstatic.com/**',lambda route: route.abort())
    # Charts are not the subject of these navigation/filter contracts. Stub only
    # the external chart renderer; all portal modules and database APIs are real.
    context.route('https://cdn.jsdelivr.net/npm/chart.js',lambda route: route.fulfill(
        content_type='application/javascript',body='window.Chart=class {destroy(){} update(){} static register(){}};'))
    yield context
    context.close()
    browser.close()
    playwright.stop()


def test_operator_queue_solarwinds_nodes_review(portal_url, browser_context):
    """Clicking 'SolarWinds nodes need review' -> 'View' navigates to Infrastructure Servers,
    applies Health Tier = Low/Critical filter, displays active filter banner, and refreshes table."""
    page = browser_context.new_page()
    page.goto(portal_url, wait_until="domcontentloaded")

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
    expect(record_count).to_contain_text(f"of {expected_count} SolarWinds Nodes")

    # Verify Clear Filter restores full list
    clear_btn = page.locator("#swClearActiveFilterBtn")
    clear_btn.click()
    expect(filter_banner).to_be_hidden()
    expect(health_select).to_have_value("")
    expect(record_count).not_to_contain_text(f"of {expected_count} SolarWinds Nodes")
    expect(record_count).to_contain_text("SolarWinds Nodes")

    page.close()


def test_location_scorecards_drilldowns_and_mobile(portal_url, browser_context):
    page = browser_context.new_page()
    errors=[]
    page.on('pageerror',lambda error: errors.append(str(error)))
    page.goto(portal_url,wait_until='domcontentloaded')
    page.locator('.nav-tab[data-view="infrastructure"]').click()
    page.locator('.category-card-tab[data-subtab="sites"]').click()
    expect(page.locator('#locCards .location-score-card')).to_have_count(2,timeout=15000)
    expect(page.locator('#catSitesSub')).to_contain_text('reporting groups')
    expect(page.locator('#locSummary')).to_contain_text('2')
    expect(page.locator('#locUnassigned')).to_contain_text('1 unassigned record')
    page.locator('#locSummary button[data-status="critical"]').click()
    expect(page.locator('#locStatus')).to_have_value('critical')
    page.locator('#locReset').click()
    pune=page.locator('.location-score-card').filter(has=page.get_by_role('button',name='Pune',exact=True))
    expect(pune.locator('.location-score-value')).to_contain_text('Red · Combined')
    expect(pune.locator('.location-score-value strong')).to_have_text('50.0')
    expect(pune.locator('.location-score-reason')).to_contain_text('Compliance 50.0%')
    expect(pune.locator('.location-score-reason')).to_contain_text('check-ins 50.0%')
    pune.get_by_role('button',name='1 noncompliant',exact=True).click()
    expect(page.locator('#locBrowse')).to_be_hidden()
    expect(page.locator('#locDevices')).to_contain_text('NONCOMPLIANT-LAPTOP')
    expect(page.locator('#locDevices .status-pill.status-critical')).to_have_text('NonCompliant')
    expect(page.locator('#locSelection')).to_contain_text('1 matching records')
    expect(page.locator('#locIssue')).to_have_value('noncompliant')
    expect(page.locator('#locDevices')).to_contain_text('10 days ago')
    page.locator('#locIssue').select_option('critical')
    expect(page.locator('#locDevices')).to_contain_text('CRITICAL-SERVER')
    expect(page.locator('#locDevices .status-pill.status-critical')).to_have_text('Critical')
    page.locator('#locClearDetail').click()
    expect(page.locator('#locSelection')).to_contain_text('4 matching records')
    page.locator('#locSource').select_option('INTUNE')
    expect(page.locator('#locSelection')).to_contain_text('2 matching records')
    expect(page.locator('#locDevices .status-pill.status-healthy')).to_have_text('Compliant')
    export=page.request.get(urljoin(page.url,page.locator('#locExport').get_attribute('href')))
    assert export.status==200 and export.headers['x-record-count']=='2'
    assert 'NONCOMPLIANT-LAPTOP' in export.text()
    page.locator('#locClose').click()
    expect(page.locator('#locBrowse')).to_be_visible()
    page.locator('#locUnassigned button').click()
    expect(page.locator('#locDevices')).to_contain_text('UNASSIGNED-LAPTOP')
    expect(page.locator('#locDetail')).to_contain_text('excluded from location scores')
    page.locator('#locClose').click()
    page.locator('#locSearch').fill('Noida')
    expect(page.locator('#locCards .location-score-card')).to_have_count(1)
    expect(page.locator('#locCards')).to_contain_text('Red · Infrastructure')
    page.locator('#locRefresh').click()
    expect(page.locator('#locSearch')).to_have_value('Noida')
    expect(page.locator('#locCards .location-score-card')).to_have_count(1)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 2')
    assert errors==[]
    page.close()


def test_location_catalogue_progressive_disclosure(portal_url, catalogue_inventory, browser_context):
    page = browser_context.new_page()
    page.goto(portal_url, wait_until='domcontentloaded')
    page.locator('.nav-tab[data-view="infrastructure"]').click()
    page.locator('.category-card-tab[data-subtab="sites"]').click()
    expect(page.locator('#locCards .location-score-card')).to_have_count(24, timeout=15000)
    expect(page.locator('#locResults')).to_contain_text('24 of 29')
    page.locator('#locShowMore').click()
    expect(page.locator('#locCards .location-score-card')).to_have_count(29)
    page.locator('#locSearch').fill('Office 01')
    expect(page.locator('#locCards .location-score-card')).to_have_count(1)
    expect(page.locator('#locSummary button[data-status="healthy"]')).to_contain_text('1')
    page.locator('#locMode').select_option('infrastructure')
    expect(page.locator('#locSummary button[data-status="unavailable"]')).to_contain_text('1')
    expect(page.locator('#locCards')).to_contain_text('No SolarWinds records')
    page.close()


def test_operator_queue_endpoints_noncompliant(portal_url, browser_context):
    """Clicking 'Endpoints are noncompliant' -> 'View' navigates to Endpoints,
    selects Compliance Status = Noncompliant, displays active filter banner, and refreshes table."""
    page = browser_context.new_page()
    page.goto(portal_url, wait_until="domcontentloaded")

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
    expect(first_status_pill).to_contain_text(re.compile("noncompliant", re.I))

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
