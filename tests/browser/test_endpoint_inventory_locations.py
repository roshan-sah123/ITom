"""Location browsing, review labels and complete exports in the actual endpoint UI."""
import csv
from pathlib import Path
import pytest
from tests.browser.test_operator_queue import browser_context, expect
from tests.factories import make_ci

pytestmark = pytest.mark.browser


@pytest.fixture
async def inventory_url(portal_url, session):
    session.add(make_ci('INTUNE', 'RESEARCHED-LAPTOP', 'Compliant', 'High',
                        location_id='pune', location_resolution='review'))
    session.add_all([make_ci('INTUNE', f'NOIDA-LAPTOP-{index:02}', 'Compliant', 'High',
                            location_id='noida', location_resolution='mapped') for index in range(12)])
    await session.commit()
    return portal_url


def open_inventory(page, url):
    page.goto(url, wait_until='domcontentloaded')
    page.locator('.nav-tab[data-view="endpoints"]').click()
    expect(page.locator('#epFilterLocation')).to_be_enabled()
    expect(page.locator('#epFilterLocation option[value="pune"]')).to_have_count(1)


def test_location_column_review_unassigned_pagination_and_reset(inventory_url, browser_context):
    page = browser_context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    open_inventory(page, inventory_url)
    expect(page.locator('#view-endpoints thead th').nth(1)).to_have_text('LOCATION')
    page.locator('#epFilterLocation').select_option('pune')
    expect(page.locator('#epRecordCount')).to_contain_text('of 3 Managed Devices')
    expect(page.locator('#epDeviceTableBody tr')).to_have_count(3)
    reviewed = page.locator('#epDeviceTableBody tr').filter(has_text='RESEARCHED-LAPTOP')
    expect(reviewed).to_contain_text('Pune')
    expect(reviewed).to_contain_text('Needs review')
    evidence = Path('output/playwright/endpoint-inventory-locations')
    evidence.mkdir(parents=True, exist_ok=True)
    page.locator('#view-endpoints .data-grid-card').screenshot(path=str(evidence/'desktop.png'))
    page.locator('#epFilterStatus').select_option('Noncompliant')
    expect(page.locator('#epRecordCount')).to_contain_text('of 1 Managed Devices')
    expect(page.locator('#epActiveFilterLabel')).to_contain_text('Pune')
    page.locator('#epResetFilters').click()
    expect(page.locator('#epFilterLocation')).to_have_value('')
    page.locator('#epFilterLocation').select_option('noida')
    page.locator('#epPageSizeSelect').select_option('10')
    expect(page.locator('#epRecordCount')).to_contain_text('of 12 Managed Devices')
    expect(page.locator('#epDeviceTableBody tr')).to_have_count(10)
    page.locator('#epPaginationControls').get_by_role('button', name='2', exact=True).click()
    expect(page.locator('#epDeviceTableBody tr')).to_have_count(2)
    page.locator('#epFilterLocation').select_option('unassigned')
    expect(page.locator('#epDeviceTableBody tr')).to_have_count(1)
    expect(page.locator('#epDeviceTableBody')).to_contain_text('Unassigned')
    expect(page.locator('#epRecordCount')).to_contain_text('Showing 1–1')
    page.locator('#epFilterStatus').select_option('Compliant')
    expect(page.locator('#epDeviceTableBody')).to_contain_text('No devices match')
    assert page.locator('#epDeviceTableBody td').get_attribute('colspan') == '7'
    page.locator('#epResetFilters').click()
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
    page.screenshot(path=str(evidence/'mobile.png'), full_page=True)
    assert not errors
    page.close()


def test_filtered_csv_contains_all_matching_rows_and_location_states(inventory_url, browser_context):
    page = browser_context.new_page()
    open_inventory(page, inventory_url)
    page.locator('#epFilterLocation').select_option('noida')
    page.locator('#epPageSizeSelect').select_option('10')
    expect(page.locator('#epDeviceTableBody tr')).to_have_count(10)
    with page.expect_download() as downloaded:
        page.locator('#epExportCsv').click()
    rows = list(csv.DictReader(Path(downloaded.value.path()).read_text(encoding='utf-8-sig').splitlines()))
    assert len(rows) == 12
    assert {row['Location'] for row in rows} == {'Noida'}
    assert {row['Location Assignment'] for row in rows} == {'Mapped'}
    page.locator('#epFilterLocation').select_option('pune')
    expect(page.locator('#epRecordCount')).to_contain_text('of 3 Managed Devices')
    with page.expect_download() as downloaded:
        page.locator('#epExportCsv').click()
    rows = list(csv.DictReader(Path(downloaded.value.path()).read_text(encoding='utf-8-sig').splitlines()))
    assert len(rows) == 3
    assert next(row for row in rows if row['Device Name']=='RESEARCHED-LAPTOP')['Location Assignment']=='Needs review'
    page.close()


def test_location_options_failure_is_retryable_without_hiding_inventory(inventory_url, browser_context):
    page = browser_context.new_page()
    page.route('**/api/v1/locations', lambda route: route.fulfill(status=503, json={'detail':'Unavailable'}))
    page.goto(inventory_url, wait_until='domcontentloaded')
    page.locator('.nav-tab[data-view="endpoints"]').click()
    expect(page.locator('#epLocationMessage')).to_contain_text('Location filter unavailable')
    expect(page.locator('#epDeviceTableBody')).to_contain_text('COMPLIANT-LAPTOP')
    page.unroute('**/api/v1/locations')
    page.locator('#epRetryLocations').click()
    expect(page.locator('#epFilterLocation')).to_be_enabled()
    page.locator('#epFilterLocation').select_option('pune')
    expect(page.locator('#epRecordCount')).to_contain_text('of 3 Managed Devices')
    page.close()
