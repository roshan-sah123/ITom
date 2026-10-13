"""CMDB accounting describes source records and clears invalid evidence."""
from pathlib import Path
import pytest
from tests.browser.test_operator_queue import browser_context, expect

pytestmark = pytest.mark.browser


def open_cmdb(page, portal_url):
    page.goto(portal_url, wait_until='domcontentloaded')
    page.locator('.nav-tab[data-view="cmdb"]').click()
    expect(page.locator('#cmdbTotalCisVal')).not_to_have_text('—')


def test_cmdb_source_accounting_and_visible_distribution(portal_url, browser_context):
    page = browser_context.new_page()
    open_cmdb(page, portal_url)
    view = page.locator('#view-cmdb')
    expect(view).to_contain_text('Total source records')
    expect(view).to_contain_text('Intune records')
    expect(view).to_contain_text('SolarWinds records')
    expect(view).to_contain_text('same physical device')
    expect(view).not_to_contain_text('HEALTH COMPLIANCE BASELINE')
    expect(page.locator('#cmdbTotalCisVal')).to_have_text('6')
    expect(page.locator('#cmdbIntuneProvVal')).to_have_text('3')
    expect(page.locator('#cmdbSwProvVal')).to_have_text('3')
    bar = page.locator('#cmdbProvenanceBar')
    expect(bar).to_have_attribute('data-status', 'snapshot')
    assert bar.bounding_box()['height'] >= 12
    width = bar.bounding_box()['width']
    for source in ['Intune', 'SolarWinds']:
        assert abs(page.locator(f'#cmdbProvenance{source}Bar').bounding_box()['width'] - width / 2) <= 2
    assert page.locator('#cmdbProvenancePanel').bounding_box()['height'] < 250
    page.locator('#cmdbFilterSource').select_option('INTUNE')
    expect(page.locator('#cmdbRecordCount')).to_contain_text('of 3')
    page.get_by_role('button', name='COMPLIANT-LAPTOP', exact=True).click()
    expect(page.locator('#slideDrawer')).to_be_visible()
    page.keyboard.press('Escape')
    output = Path('outputs/cmdb-clarity')
    output.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(output / 'desktop.png'), full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
    page.screenshot(path=str(output / 'mobile.png'), full_page=True)
    page.close()


@pytest.mark.parametrize('payload,expected', [
    ({'total_cis': 3, 'total_endpoints': 0, 'total_servers': 2, 'total_network_devices': 1, 'total_unclassified': 0}, '0'),
    ({'total_cis': 0, 'total_endpoints': 0, 'total_servers': 0, 'total_network_devices': 0, 'total_unclassified': 0}, '0'),
    ({'total_cis': 6, 'total_endpoints': 3, 'total_servers': 1, 'total_network_devices': 1, 'total_unclassified': 0}, 'Unavailable'),
    ({'total_cis': 6, 'total_endpoints': None, 'total_servers': 2, 'total_network_devices': 1, 'total_unclassified': 0}, 'Unavailable'),
    ({'total_cis': 0, 'data_available': False}, 'Unavailable'),
])
def test_source_zero_empty_and_inconsistent_totals(portal_url, browser_context, payload, expected):
    page = browser_context.new_page()
    page.route('**/api/v1/cmdb/summary', lambda route: route.fulfill(json=payload))
    open_cmdb(page, portal_url)
    expect(page.locator('#cmdbIntuneProvVal')).to_have_text(expected)
    if expected == 'Unavailable':
        expect(page.locator('#cmdbProvenanceBar')).to_have_attribute('data-status', 'unavailable')
        expect(page.locator('#cmdbTotalCisVal')).to_have_text('Unavailable')
    elif payload['total_cis'] == 0:
        expect(page.locator('#cmdbProvenanceStatus')).to_contain_text('No stored source records')
    else:
        expect(page.locator('#cmdbProvenanceSolarWindsLabel')).to_contain_text('100.0%')
    page.close()


def test_failed_reload_clears_previous_cmdb_totals(portal_url, browser_context):
    page = browser_context.new_page()
    open_cmdb(page, portal_url)
    expect(page.locator('#cmdbTotalCisVal')).to_have_text('6')
    page.route('**/api/v1/cmdb/summary', lambda route: route.fulfill(status=503, body='{}'))
    page.locator('#workspaceFreshness-cmdb').get_by_role('button', name='Reload snapshot', exact=True).click()
    expect(page.locator('#cmdbTotalCisVal')).to_have_text('Unavailable')
    expect(page.locator('#cmdbProvenanceIntuneLabel')).to_contain_text('Unavailable')
    expect(page.locator('#cmdbProvenanceIntuneBar')).to_have_css('width', '0px')
    expect(page.locator('#cmdbTableBody')).to_contain_text('COMPLIANT-LAPTOP')
    page.close()
