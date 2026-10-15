"""VP health view contracts, using isolated source records and real APIs."""
from pathlib import Path
import pytest

from tests.browser.test_operator_queue import browser_context, expect
from tests.browser.test_location_scorecard_clarity import open_scores

pytestmark = pytest.mark.browser


def test_location_summary_filters_counts_and_selection(portal_url, catalogue_inventory, browser_context):
    page = browser_context.new_page()
    open_scores(page, portal_url)
    for status in ['healthy', 'warning', 'critical', 'unavailable']:
        button = page.locator(f'#locSummary button[data-status="{status}"]')
        count = int(button.locator('strong').inner_text().replace(',', ''))
        button.click()
        expect(page.locator('#locStatus')).to_have_value(status)
        expect(page.locator(f'#locSummary button[data-status="{status}"]')).to_have_attribute('aria-pressed', 'true')
        expect(page.locator('#locCards .location-score-card')).to_have_count(min(count, 24))
        assert page.locator('#locCards .location-score-card').evaluate_all(
            '(cards, status) => cards.every(card => card.classList.contains("score-" + status))', status)
    page.locator('#locReset').click()
    page.locator('#locSearch').fill('Pune')
    expect(page.locator('#locCards .location-record-counts')).to_have_text('2 endpoints · 2 nodes')
    captures = Path('output/playwright/vp-dashboard')
    captures.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(captures / 'desktop.png'), full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.locator('.infra-category-grid').evaluate(
        '(el) => getComputedStyle(el).gridTemplateColumns.split(" ").length') == 2
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
    page.screenshot(path=str(captures / 'mobile.png'), full_page=True)
    page.close()


def test_network_health_filters_real_counts_and_export(portal_url, browser_context):
    page = browser_context.new_page()
    page.goto(portal_url, wait_until='domcontentloaded')
    page.locator('.nav-tab[data-view="infrastructure"]').click()
    page.locator('.category-card-tab[data-subtab="networks"]').click()
    select = page.locator('#netFilterHealth')
    expect(select).to_be_visible()
    select.select_option('Low')
    expect(page.locator('#netDeviceTableBody')).to_contain_text('DOWN-SWITCH')
    expect(page.locator('#netRecordCount')).to_contain_text('of 1 Network Devices')
    with page.expect_download() as captured:
        page.locator('#netExportCsv').click()
    with open(captured.value.path(), encoding='utf-8-sig') as exported:
        assert 'DOWN-SWITCH' in exported.read()
    select.select_option('High')
    expect(page.locator('#netRecordCount')).to_contain_text('of 0 Network Devices')
    page.close()


@pytest.mark.parametrize('view,control,values', [
    ('infrastructure', 'swFilterHealth', ['High', 'Medium', 'Low']),
    ('infrastructure', 'swFilterStatus', ['Up', 'Warning', 'Down']),
    ('endpoints', 'epFilterStatus', ['Compliant', 'ConfigManager', 'Noncompliant']),
    ('cmdb', 'cmdbFilterHealth', ['High', 'Medium', 'Low']),
])
def test_status_filters_have_semantic_selected_surfaces(portal_url, browser_context, view, control, values):
    page = browser_context.new_page()
    page.goto(portal_url, wait_until='domcontentloaded')
    page.locator(f'.nav-tab[data-view="{view}"]').click()
    select = page.locator(f'#{control}')
    expect(select).to_be_visible()
    neutral = select.evaluate('(el) => getComputedStyle(el).backgroundColor')
    colours = []
    for value in values:
        select.select_option(value)
        colours.append(select.evaluate('(el) => getComputedStyle(el).backgroundColor'))
    assert all(colour != neutral for colour in colours)
    assert len(set(colours)) == 3
    select.select_option('')
    assert select.evaluate('(el) => getComputedStyle(el).backgroundColor') == neutral
    page.close()
