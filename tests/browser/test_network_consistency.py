"""Network investigation and missing evidence stay consistent with CMDB."""
import csv
import pytest
from tests.browser.test_operator_queue import browser_context, expect

pytestmark = pytest.mark.browser


def open_networks(page, portal_url):
    page.goto(portal_url, wait_until='domcontentloaded')
    page.locator('.nav-tab[data-view="infrastructure"]').click()
    page.locator('.category-card-tab[data-subtab="networks"]').click()
    expect(page.locator('#netDeviceTableBody')).to_contain_text('DOWN-SWITCH')


def test_network_status_and_keyboard_drilldown(portal_url, browser_context):
    page = browser_context.new_page()
    open_networks(page, portal_url)
    row = page.locator('#netDeviceTableBody tr').filter(has_text='DOWN-SWITCH')
    expect(row.locator('td').nth(2).locator('.status-pill')).to_have_class('status-pill status-neutral')
    expect(row.locator('td').nth(4).locator('.status-pill')).to_have_class('status-pill status-critical')
    expect(row.locator('td').nth(5)).to_contain_text('Low')
    expect(row.locator('td').nth(5).locator('.status-pill')).to_have_class('status-pill status-critical')
    trigger = row.get_by_role('button', name='DOWN-SWITCH', exact=True)
    trigger.press('Enter')
    expect(page.locator('#slideDrawer')).to_be_visible()
    expect(page.locator('#drawerContent')).to_contain_text('SOLARWINDS-DOWN-SWITCH')
    page.keyboard.press('Escape')
    expect(trigger).to_be_focused()
    page.close()


def test_cmdb_observed_health_tiers_keep_colors(portal_url, browser_context):
    page = browser_context.new_page()
    page.goto(portal_url, wait_until='domcontentloaded')
    page.locator('.nav-tab[data-view="cmdb"]').click()
    for name, tier, color in [
        ('HEALTHY-SERVER', 'High', 'healthy'),
        ('CRITICAL-SERVER', 'Low', 'critical'),
        ('UNASSIGNED-LAPTOP', 'Medium', 'warning'),
    ]:
        row = page.locator('#cmdbTableBody tr').filter(has_text=name)
        health = row.locator('td').nth(5).locator('.status-pill')
        expect(health).to_have_text(tier)
        expect(health).to_have_class(f'status-pill status-{color}')
    page.close()


@pytest.mark.parametrize('workspace,endpoint,table,export_button', [
    ('infrastructure', 'solarwinds/network-devices', 'netDeviceTableBody', 'netExportCsv'),
    ('cmdb', 'cmdb/cis', 'cmdbTableBody', 'cmdbExportCsv'),
])
def test_missing_health_neutral_on_screen_and_export(portal_url, browser_context, workspace, endpoint, table, export_button):
    page = browser_context.new_page()

    def missing_health(route):
        response = route.fetch()
        payload = response.json()
        data = payload.get('data', payload)
        for item in data['items']:
            item['health_tier'] = None
        route.fulfill(response=response, json=payload)

    page.route(f'**/api/v1/{endpoint}?*', missing_health)
    page.goto(portal_url, wait_until='domcontentloaded')
    page.locator(f'.nav-tab[data-view="{workspace}"]').click()
    if workspace == 'infrastructure':
        page.locator('.category-card-tab[data-subtab="networks"]').click()
    health = page.locator(f'#{table} tr').first.locator('td').nth(5).locator('.status-pill')
    expect(health).to_have_text('Unknown')
    expect(health).to_have_class('status-pill status-unknown')
    with page.expect_download() as captured:
        page.locator(f'#{export_button}').click()
    with open(captured.value.path(), encoding='utf-8-sig', newline='') as exported:
        rows = list(csv.DictReader(exported))
    assert rows
    assert all(row['Health Tier'] == 'Unknown' for row in rows)
    page.close()


def test_network_filters_have_one_handler_after_navigation(portal_url, browser_context):
    page = browser_context.new_page()
    open_networks(page, portal_url)
    page.locator('.nav-tab[data-view="cmdb"]').click()
    page.locator('.nav-tab[data-view="infrastructure"]').click()
    page.locator('.category-card-tab[data-subtab="networks"]').click()
    calls = []
    page.on('request', lambda request: calls.append(request.url) if '/solarwinds/network-devices?' in request.url and 'ci_type=switch' in request.url else None)
    page.locator('#netFilterType').select_option('switch')
    expect(page.locator('#netDeviceTableBody')).to_contain_text('DOWN-SWITCH')
    page.wait_for_timeout(350)
    assert len(calls) == 1
    page.close()
