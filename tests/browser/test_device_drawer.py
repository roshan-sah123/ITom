"""Device investigation must work across inventory workspaces and API failures."""
import re
from pathlib import Path
import pytest
from tests.browser.test_operator_queue import browser_context, expect

pytestmark = pytest.mark.browser


@pytest.mark.parametrize('workspace,name', [
    ('infrastructure', 'CRITICAL-SERVER'),
    ('endpoints', 'NONCOMPLIANT-LAPTOP'),
    ('cmdb', 'COMPLIANT-LAPTOP'),
])
def test_inventory_details_and_keyboard(portal_url, browser_context, workspace, name):
    page = browser_context.new_page()
    page.goto(portal_url, wait_until='domcontentloaded')
    page.locator(f'.nav-tab[data-view="{workspace}"]').click()
    trigger = page.locator(f'#view-{workspace} .ci-name-link').filter(has_text=re.compile(f'^{name}$'))
    trigger.click()
    drawer = page.locator('#slideDrawer')
    expect(drawer).to_be_visible()
    expect(drawer).to_contain_text(name)
    expect(drawer).to_contain_text('Last synchronized')
    expect(drawer).to_contain_text('No status changes recorded')
    expect(page.locator('#drawerCloseBtn')).to_be_focused()
    output = Path('outputs/device-drawer')
    output.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(output / f'{workspace}-desktop.png'))
    page.keyboard.press('Shift+Tab')
    expect(page.locator('#drawerCloseBtn')).to_be_focused()
    page.keyboard.press('Escape')
    expect(drawer).to_be_hidden()
    expect(trigger).to_be_focused()
    trigger.press('Enter')
    expect(drawer).to_be_visible()
    page.locator('#drawerCloseBtn').click()
    expect(drawer).to_be_hidden()
    expect(trigger).to_be_focused()
    page.set_viewport_size({'width': 390, 'height': 844})
    trigger.click()
    expect(drawer).to_be_visible()
    assert drawer.bounding_box()['width'] <= 390
    page.screenshot(path=str(output / f'{workspace}-mobile.png'))
    page.keyboard.press('Escape')
    page.close()


def test_detail_failure_and_backdrop_close(portal_url, browser_context):
    page = browser_context.new_page()
    page.route('**/api/v1/cmdb/cis/*', lambda route: route.fulfill(status=503, body='Unavailable'))
    page.goto(portal_url, wait_until='domcontentloaded')
    page.locator('.nav-tab[data-view="endpoints"]').click()
    trigger = page.get_by_role('button', name='NONCOMPLIANT-LAPTOP', exact=True)
    trigger.click()
    expect(page.locator('#drawerContent')).to_contain_text('Device details unavailable')
    page.locator('#drawerBackdrop').click(position={'x': 10, 'y': 10})
    expect(page.locator('#slideDrawer')).to_be_hidden()
    expect(trigger).to_be_focused()
    page.close()


def test_late_history_does_not_replace_another_device(portal_url, browser_context):
    page = browser_context.new_page()
    pending = []
    page.route('**/api/v1/cmdb/cis/*/history?*', lambda route: pending.append(route))
    page.goto(portal_url, wait_until='domcontentloaded')
    page.locator('.nav-tab[data-view="infrastructure"]').click()
    page.get_by_role('button', name='CRITICAL-SERVER', exact=True).click()
    expect(page.locator('#drawerHistoryList')).to_contain_text('Loading recorded changes')
    page.wait_for_timeout(100)
    page.keyboard.press('Escape')
    page.get_by_role('button', name='HEALTHY-SERVER', exact=True).click()
    expect(page.locator('#drawerContent')).to_contain_text('SOLARWINDS-HEALTHY-SERVER')
    pending[0].fulfill(json=[{'status': 'OLD-DEVICE-HISTORY', 'health_tier': 'Low'}])
    expect(page.locator('#drawerCiTitle')).to_have_text('HEALTHY-SERVER')
    expect(page.locator('#drawerHistoryList')).not_to_contain_text('OLD-DEVICE-HISTORY')
    page.keyboard.press('Escape')
    page.close()


def test_history_failure_is_not_healthy_state(portal_url, browser_context):
    page = browser_context.new_page()
    page.route('**/api/v1/cmdb/cis/*/history?*', lambda route: route.fulfill(status=503, body='Unavailable'))
    page.goto(portal_url, wait_until='domcontentloaded')
    page.locator('.nav-tab[data-view="infrastructure"]').click()
    page.locator('#view-infrastructure .ci-name-link').filter(has_text='CRITICAL-SERVER').click()
    expect(page.locator('#slideDrawer')).to_be_visible()
    expect(page.locator('#drawerHistoryList')).to_contain_text('History unavailable')
    expect(page.locator('#drawerContent')).not_to_contain_text('State steady')
    page.close()
