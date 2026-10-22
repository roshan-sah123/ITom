"""Actual browser -> API -> isolated CMDB group hierarchy journeys."""
from pathlib import Path
from urllib.parse import urljoin
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from tests.browser.test_operator_queue import browser_context, expect
from tests.test_solarwinds_groups import GroupClient, ingest

pytestmark = pytest.mark.browser


@pytest_asyncio.fixture
async def group_inventory(operator_inventory, session, monkeypatch):
    from app.services.location_service import LocationService
    # This fixture supplies its own canonical catalogue; do not install production seeds.
    monkeypatch.setattr(LocationService, 'install_seed', AsyncMock())
    from tests.test_group_scores import native_client
    client = native_client()
    client.nodes[1]['Status'] = 14
    assert (await ingest(session, client))['status'] == 'SUCCESS'


def open_groups(page, url):
    page.goto(url, wait_until='networkidle')
    page.locator('.nav-tab[data-view="infrastructure"]').click()
    page.locator('.category-card-tab[data-subtab="sites"]').click()
    expect(page.locator('#swGroupTree')).to_be_visible()


def test_expand_drilldown_filters_back_and_drawer(portal_url, group_inventory, browser_context):
    page = browser_context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    open_groups(page, portal_url)
    expect(page.locator('#swGroupTree')).not_to_contain_text('MAPS-private')
    expect(page.locator('#swGroupTree')).to_contain_text('Empty  (Kraków, Poland)')
    root = page.locator('[data-group-path="10"]')
    expect(root.locator('.status-pill')).to_have_text('Critical')
    toggle = root.get_by_role('button', name='Expand BOCBA(Bolivia,Cochabamba-Encora)', exact=True)
    toggle.focus(); page.keyboard.press('Enter')
    expect(page.locator('[data-group-path="10/11"]')).to_be_visible()
    name = root.get_by_role('button', name='BOCBA(Bolivia,Cochabamba-Encora)', exact=True)
    name.click()
    expect(page.locator('#swGroupDevices tr')).to_have_count(2)
    expect(page.locator('#swGroupDevices')).not_to_contain_text('Device 3')
    page.locator('#swGroupDeviceStatus').select_option('Critical')
    expect(page.locator('#swGroupDevices tr')).to_have_count(1)
    expect(page.locator('#swGroupDevices')).to_contain_text('Device 2')
    page.locator('#swGroupDeviceSearch').fill('missing')
    expect(page.locator('#swGroupDevices')).to_contain_text('No devices found')
    page.locator('#swGroupResetDevices').click()
    expect(page.locator('#swGroupDevices tr')).to_have_count(2)
    page.locator('#swGroupDevices').get_by_role('button', name='Device 1', exact=True).click()
    expect(page.locator('#slideDrawer')).to_be_visible()
    page.keyboard.press('Escape')
    expect(page.locator('#swGroupDevices').get_by_role('button', name='Device 1', exact=True)).to_be_focused()
    page.locator('#swGroupBack').click()
    expect(name).to_be_focused()
    expect(page.locator('[data-group-path="10/11"]')).to_be_visible()
    page.locator('#swGroupSearch').fill('Empty')
    expect(page.locator('#swGroupTree > li')).to_have_count(1)
    page.get_by_role('button', name='Empty  (Kraków, Poland)', exact=True).click()
    expect(page.locator('#swGroupDevices')).to_contain_text('No devices found')
    page.locator('#swGroupBack').click()
    expect(page.locator('#swGroupSearch')).to_have_value('Empty')
    output = Path('output/playwright/solarwinds-groups'); output.mkdir(parents=True, exist_ok=True)
    page.locator('#swGroupSearch').fill('')
    page.screenshot(path=str(output / 'desktop.png'), full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
    page.screenshot(path=str(output / 'mobile.png'), full_page=True)
    page.locator('#locMode').select_option('endpoints')
    expect(page.locator('#intuneLocationTree')).to_be_visible()
    expect(page.locator('#swGroupTree')).to_have_count(0)
    page.locator('#locMode').select_option('combined')
    expect(page.locator('#locMode')).to_have_value('combined')
    page.locator('#locMode').select_option('infrastructure')
    expect(page.locator('#swGroupTree')).to_be_visible()
    assert errors == []
    page.close()


def test_error_retry_and_unsynced_states(portal_url, browser_context):
    page = browser_context.new_page()
    page.route('**/api/v1/solarwinds/groups', lambda route: route.fulfill(status=503, json={'detail':'Unavailable'}))
    page.goto(portal_url, wait_until='networkidle')
    page.locator('.nav-tab[data-view="infrastructure"]').click()
    page.locator('.category-card-tab[data-subtab="sites"]').click()
    expect(page.locator('#swGroupMessage')).to_contain_text('Group data unavailable')
    page.unroute('**/api/v1/solarwinds/groups')
    page.locator('#swGroupRetry').click()
    expect(page.locator('#swGroupMessage')).to_contain_text('No successful SolarWinds group snapshot yet')
    page.close()
