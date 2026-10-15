"""SolarWinds location rows use existing catalogue scores and real drilldowns."""
from pathlib import Path
from urllib.parse import urljoin

import pytest
import pytest_asyncio
from app.models.location import Location
from tests.factories import make_ci
from tests.browser.test_operator_queue import browser_context, expect
from tests.browser.test_location_scorecard_clarity import open_scores

pytestmark = pytest.mark.browser


@pytest.mark.parametrize('name,label,count', [('Green site','Green',1), ('Amber site','Amber',5), ('Red site','Red',2), ('Unknown site','Insufficient data',1)])
def test_status_badge_opens_location_nodes(portal_url, solarwinds_locations, browser_context, name, label, count):
    page = browser_context.new_page()
    open_scores(page, portal_url)
    page.locator('#locMode').select_option('infrastructure')
    row = page.locator('#locSolarWindsRows tr').filter(has=page.get_by_role('button', name=name, exact=True))
    badge = row.get_by_role('button', name=f'View {label} inventory for {name}', exact=True)
    expect(badge).to_be_visible()
    badge.focus()
    page.keyboard.press('Enter')
    expect(page.locator('#locDetailTitle')).to_have_text(f'{name} inventory')
    expect(page.locator('#locSource')).to_have_value('SOLARWINDS')
    expect(page.locator('#locDevices tr')).to_have_count(count)
    expect(page.locator('#locSelection')).to_contain_text(f'{count} matching records')
    page.locator('#locClose').click()
    expect(badge).to_be_focused()
    badge.click()
    expect(page.locator('#locDevices tr')).to_have_count(count)
    page.close()


@pytest_asyncio.fixture
async def solarwinds_locations(operator_inventory, session):
    for name, states in [('Green site', ['Up']), ('Amber site', ['Up'] * 4 + ['Warning']),
                         ('Red site', ['Down', 'Critical']), ('Unknown site', ['Unmanaged'])]:
        session.add(Location(id=name, name=name, level='office'))
        await session.flush()
        for index, status in enumerate(states):
            session.add(make_ci('SOLARWINDS', f'{name}-{index}', status, 'High',
                                location_id=name, location_resolution='mapped'))
    await session.commit()


def test_rows_match_catalogue_and_solarwinds_drilldown(portal_url, catalogue_inventory, solarwinds_locations, browser_context):
    page = browser_context.new_page()
    catalogue = page.request.get(urljoin(portal_url, '/api/v1/locations')).json()['data']['items']
    expected = [loc for loc in catalogue if loc['id'] != 'unassigned' and loc['nodes']]
    open_scores(page, portal_url)
    page.locator('#locMode').select_option('infrastructure')
    expect(page.locator('#locUnassigned')).to_contain_text('0 unassigned nodes')
    expect(page.locator('#locCoverage [data-source="INTUNE"]')).to_be_hidden()
    expect(page.locator('#locSolarWindsRows tr')).to_have_count(len(expected))
    expect(page.locator('#locSummary button[data-status=""] strong')).to_have_text(str(len(expected)))
    assert page.locator('#locCards thead th').all_text_contents() == [
        'Location name', 'Total nodes', 'Up', 'Warning', 'Down/Critical', 'Health score', 'Status']
    labels = {'healthy': 'Green', 'warning': 'Amber', 'critical': 'Red', 'unavailable': 'Insufficient data'}
    for loc in expected:
        row = page.locator('#locSolarWindsRows tr').filter(has=page.get_by_role('button', name=loc['name'], exact=True))
        score = loc['scores']['infrastructure']
        assert row.locator('td').all_text_contents() == [loc['name'], str(loc['nodes']), str(loc['issues']['up']),
            str(loc['issues']['warning']), str(loc['issues']['down'] + loc['issues']['critical']),
            '—' if score['value'] is None else f"{score['value']:.1f}%", labels[score['status']]]
    for status in labels:
        page.locator(f'#locSummary button[data-status="{status}"]').click()
        expect(page.locator('#locSolarWindsRows tr')).to_have_count(
            sum(loc['scores']['infrastructure']['status'] == status for loc in expected))
    page.locator('#locStatus').select_option('')
    page.locator('#locLevel').select_option('office')
    expect(page.locator('#locSolarWindsRows tr')).to_have_count(4)
    page.locator('#locLevel').select_option('')
    page.locator('#locSearch').fill('No matching site')
    expect(page.locator('#locSolarWindsRows tr')).to_have_count(0)
    expect(page.locator('#locCards')).to_contain_text('No SolarWinds locations match')
    page.locator('#locSearch').fill('Pune')
    expect(page.locator('#locSolarWindsRows tr')).to_have_count(1)
    button = page.get_by_role('button', name='Pune', exact=True)
    button.focus()
    page.keyboard.press('Enter')
    expect(page.locator('#locSource')).to_have_value('SOLARWINDS')
    expect(page.locator('#locDevices tr')).to_have_count(2)
    expect(page.locator('#locDevices')).not_to_contain_text('LAPTOP')
    with page.expect_download() as captured:
        page.locator('#locExport').click()
    with open(captured.value.path(), encoding='utf-8-sig') as exported:
        csv = exported.read()
        assert 'CRITICAL-SERVER' in csv and 'HEALTHY-SERVER' in csv and 'LAPTOP' not in csv
    page.locator('#locIssue').select_option('critical')
    expect(page.locator('#locDevices tr')).to_have_count(1)
    page.locator('#locClearDetail').click()
    expect(page.locator('#locSource')).to_have_value('SOLARWINDS')
    expect(page.locator('#locDevices tr')).to_have_count(2)
    page.locator('#locClose').click()
    expect(button).to_be_focused()
    captures = Path('output/playwright/solarwinds-location-rows')
    captures.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(captures / 'desktop.png'), full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
    page.screenshot(path=str(captures / 'mobile.png'), full_page=True)
    page.locator('#locMode').select_option('endpoints')
    expect(page.locator('#locCards .location-score-card').first).to_be_visible()
    expect(page.locator('#locSolarWindsRows')).to_have_count(0)
    page.close()


def test_stale_solarwinds_score_remains_unavailable(portal_url, browser_context):
    page = browser_context.new_page()
    payload = page.request.get(urljoin(portal_url, '/api/v1/locations')).json()
    pune = next(loc for loc in payload['data']['items'] if loc['id'] == 'pune')
    pune['scores']['infrastructure'] = dict(value=None, status='unavailable', reason='Source data is stale or unavailable')
    pune['freshness']['SOLARWINDS']['status'] = 'STALE'
    pune['components']['node_status']['usable'] = False
    page.route('**/api/v1/locations', lambda route: route.fulfill(json=payload))
    open_scores(page, portal_url)
    page.locator('#locMode').select_option('infrastructure')
    row = page.locator('#locSolarWindsRows tr').filter(has=page.get_by_role('button', name='Pune', exact=True))
    expect(row.locator('td').nth(5)).to_have_text('—')
    expect(row.locator('td').nth(6)).to_have_text('Insufficient data')
    expect(row.locator('td').nth(6).locator('button')).to_have_attribute('title', 'Source data is stale or unavailable. Refresh evidence before assessing health.')
    page.close()
