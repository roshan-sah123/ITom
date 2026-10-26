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


def test_combined_uses_native_groups_without_inventing_location_links(portal_url, group_inventory, browser_context):
    page = browser_context.new_page()
    errors = []
    requests = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda request: requests.append((request.method, request.url)))
    open_groups(page, portal_url)
    names = page.locator('#swGroupTree > li > .sw-group-row .sw-group-name').all_text_contents()
    count = page.locator('#catSitesVal').inner_text()

    page.locator('#locMode').select_option('combined')
    expect(page.locator('#swGroupTree')).to_be_visible()
    expect(page.locator('#locMode')).to_have_value('combined')
    assert page.locator('#swGroupTree > li > .sw-group-row .sw-group-name').all_text_contents() == names
    expect(page.locator('#catSitesVal')).to_have_text(count)
    expect(page.locator('#locCards')).to_have_count(0)
    page.get_by_role('button', name='BOCBA(Bolivia,Cochabamba-Encora)', exact=True).click()
    expect(page.locator('#swGroupDetail')).to_contain_text('An explicit approved Intune location link is required')
    expect(page.locator('#swGroupDevices tr')).to_have_count(2)
    page.locator('#swGroupRefresh').click()
    expect(page.locator('#locMode')).to_have_value('combined')
    expect(page.locator('#swGroupDetail')).to_contain_text('An explicit approved Intune location link is required')
    assert any('score_mode=combined' in url for method, url in requests)
    assert all(method == 'GET' for method, url in requests if '/api/v1/' in url)
    assert errors == []
    page.close()


def test_mapping_workbench_previews_without_approving(portal_url, group_inventory, browser_context):
    page = browser_context.new_page()
    errors, requests = [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda request: requests.append((request.method, request.url)))
    open_groups(page, portal_url)
    expect(page.locator('#swMappingToggle')).to_have_count(0)
    expect(page.locator('#swGroupTree > li')).not_to_have_count(0)
    root_count = page.locator('#swGroupTree > li').count()
    page.locator('#locMode').select_option('combined')
    expect(page.locator('#swMappingSummary')).to_contain_text('Scoreable')
    expect(page.locator('#swMappingSummary')).to_contain_text('Unmapped')
    page.locator('#swMappingToggle').click()
    expect(page.locator('#swMappingRows tr')).to_have_count(root_count)
    page.locator('#swMappingFilter').select_option('empty')
    expect(page.locator('#swMappingRows tr')).to_have_count(2)
    expect(page.locator('#swMappingRows')).to_contain_text('Empty  (Kraków, Poland)')
    page.locator('#swMappingFilter').select_option('unmapped')
    expect(page.locator('#swMappingRows tr')).to_have_count(root_count)
    page.route('**/api/v1/locations', lambda route: route.fulfill(status=503, json={'detail':'Unavailable'}))
    page.locator('#swMappingRows [data-preview-group="10"]').click()
    expect(page.locator('#swMappingPreview')).to_contain_text('Intune location catalogue unavailable')
    page.unroute('**/api/v1/locations')
    page.locator('#swMappingRetry').click()
    expect(page.locator('#swMappingPreview')).to_contain_text('BOCBA(Bolivia,Cochabamba-Encora)')
    expect(page.locator('#swMappingLocation')).to_have_value('')
    page.locator('#swMappingLocation').select_option('pune')
    expect(page.locator('#swMappingPopulation')).to_contain_text('2 Intune endpoints')
    expect(page.locator('#swMappingPopulation')).to_contain_text('2 SolarWinds devices')
    expect(page.locator('#swMappingPreview')).to_contain_text('Preview only')
    expect(page.locator('#swMappingPreview')).to_contain_text('Current link: Unmapped')
    after = page.request.get(urljoin(portal_url, '/api/v1/solarwinds/groups/10/summary?score_mode=combined'))
    assert after.json()['data']['mapping']['status'] == 'UNMAPPED'
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
    assert all(method == 'GET' for method, url in requests if '/api/v1/' in url)
    assert errors == []
    page.close()


def test_outside_groups_inventory_filters_and_drawer(portal_url, group_inventory, browser_context):
    page = browser_context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    open_groups(page, portal_url)
    page.locator('#swGroupOutsideInventory').click()
    expect(page.locator('#swOutsideDevices tr')).to_have_count(2)
    expect(page.locator('#swOutsideDevices')).to_contain_text('Device 3')
    expect(page.locator('#swOutsideDevices')).not_to_contain_text('Device 1')
    page.locator('#swOutsideSearch').fill('Device 3')
    expect(page.locator('#swOutsideSelection')).to_contain_text('1 matching device')
    expect(page.locator('#swOutsideDevices tr')).to_have_count(1)
    page.locator('#swOutsideDevices').get_by_role('button', name='Device 3', exact=True).click()
    expect(page.locator('#slideDrawer')).to_be_visible()
    page.keyboard.press('Escape')
    expect(page.locator('#swOutsideDevices').get_by_role('button', name='Device 3', exact=True)).to_be_focused()
    page.locator('#swOutsideReset').click()
    expect(page.locator('#swOutsideSelection')).to_contain_text('2 matching devices')
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
    page.locator('#swOutsideClose').click()
    expect(page.locator('#swOutsideInventory')).to_be_hidden()
    expect(page.locator('#swGroupOutsideInventory')).to_be_focused()
    assert errors == []
    page.close()


def test_error_retry_and_unsynced_states(portal_url, browser_context):
    page = browser_context.new_page()
    page.route('**/api/v1/solarwinds/groups', lambda route: route.fulfill(status=503, json={'detail':'Unavailable'}))
    page.goto(portal_url, wait_until='networkidle')
    page.locator('.nav-tab[data-view="infrastructure"]').click()
    page.locator('.category-card-tab[data-subtab="sites"]').click()
    expect(page.locator('#swGroupMessage')).to_contain_text('Group data unavailable')
    page.locator('#locMode').select_option('combined')
    expect(page.locator('#swMappingSummary')).to_have_text('Mapping readiness unavailable.')
    expect(page.locator('#swMappingToggle')).to_be_disabled()
    page.unroute('**/api/v1/solarwinds/groups')
    page.locator('#swGroupRetry').click()
    expect(page.locator('#swGroupMessage')).to_contain_text('No successful SolarWinds group snapshot yet')
    page.close()
