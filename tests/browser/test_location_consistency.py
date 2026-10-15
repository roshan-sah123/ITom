"""Location source scope stays consistent across counts and inventory controls."""
from urllib.parse import urljoin
import re

import pytest
from tests.browser.test_operator_queue import browser_context, expect
from tests.browser.test_location_scorecard_clarity import open_scores
from tests.browser.test_solarwinds_location_rows import solarwinds_locations

pytestmark = pytest.mark.browser


def test_source_inventory_controls_and_reset(portal_url, browser_context):
    page = browser_context.new_page()
    open_scores(page, portal_url)
    page.locator('#locMode').select_option('infrastructure')
    page.get_by_role('button', name='Pune', exact=True).click()
    expect(page.locator('#locDevices tr')).to_have_count(2)
    assert 'noncompliant' not in page.locator('#locIssue option').evaluate_all('(options) => options.map(o => o.value)')
    expect(page.locator('#locDetail thead')).not_to_contain_text('Last Intune check-in')
    assert page.locator('#locDevices tr').first.locator('td').count() == 4
    page.locator('#locDeviceSearch').fill('no such node')
    expect(page.locator('#locDevices')).to_contain_text('No devices found')
    expect(page.locator('#locDevices td')).to_have_attribute('colspan', '4')
    page.locator('#locDeviceSearch').fill('')
    expect(page.locator('#locSelection')).to_contain_text('2 matching records')
    page.locator('#locIssue').select_option('critical')
    expect(page.locator('#locSelection')).to_contain_text('1 matching records')
    page.locator('#locSource').select_option('INTUNE')
    expect(page.locator('#locIssue')).to_have_value('all')
    expect(page.locator('#locSelection')).to_contain_text('2 matching records')
    assert 'critical' not in page.locator('#locIssue option').evaluate_all('(options) => options.map(o => o.value)')
    expect(page.locator('#locDetail thead')).to_contain_text('Last Intune check-in')
    page.locator('#locIssue').select_option('noncompliant')
    expect(page.locator('#locSelection')).to_contain_text('1 matching records')
    page.locator('#locSource').select_option('SOLARWINDS')
    expect(page.locator('#locIssue')).to_have_value('all')
    expect(page.locator('#locSelection')).to_contain_text('2 matching records')
    page.locator('#locSource').select_option('')
    expect(page.locator('#locIssue option[value="noncompliant"]')).to_have_count(1)
    expect(page.locator('#locIssue option[value="critical"]')).to_have_count(1)
    page.locator('#locClearDetail').click()
    expect(page.locator('#locSource')).to_have_value('SOLARWINDS')
    expect(page.locator('#locSelection')).to_contain_text('2 matching records')
    page.locator('#locClose').click()
    page.locator('#locReset').click()
    expect(page.locator('#locMode')).to_have_value('infrastructure')
    page.close()


def test_reporting_group_count_matches_source(portal_url, catalogue_inventory, browser_context):
    page = browser_context.new_page()
    catalogue = page.request.get(urljoin(portal_url, '/api/v1/locations')).json()['data']['items']
    open_scores(page, portal_url)
    for mode, source in [('infrastructure', 'SolarWinds'), ('endpoints', 'Intune')]:
        key = 'nodes' if mode == 'infrastructure' else 'endpoints'
        count = sum(loc['id'] != 'unassigned' and loc[key] > 0 for loc in catalogue)
        page.locator('#locMode').select_option(mode)
        expect(page.locator('#catSitesVal')).to_have_text(str(count))
        expect(page.locator('#catSitesSub')).to_contain_text(source)
        expect(page.locator('#locSummary button[data-status=""] strong')).to_have_text(str(count))
    page.close()


def test_monitored_denominator_and_neutral_unmanaged(portal_url, solarwinds_locations, browser_context):
    page = browser_context.new_page()
    open_scores(page, portal_url)
    page.locator('#locMode').select_option('infrastructure')
    green = page.locator('#locSolarWindsRows tr').filter(has=page.get_by_role('button', name='Green site', exact=True))
    expect(green.locator('td').nth(5).locator('span')).to_have_attribute('title', re.compile('1 / 1 monitored nodes'))
    page.get_by_role('button', name='Unknown site', exact=True).click()
    expect(page.locator('#locDevices .status-unknown')).to_have_text('Unmanaged')
    page.close()


def test_endpoint_card_only_offers_endpoint_issues(portal_url, browser_context):
    page = browser_context.new_page()
    open_scores(page, portal_url)
    page.locator('#locMode').select_option('endpoints')
    pune = page.locator('.location-score-card').filter(has=page.get_by_role('button', name='Pune', exact=True))
    pune.locator('details.location-card-details summary').click()
    for issue in ['critical', 'down', 'warning', 'unmanaged']:
        expect(pune.locator(f'.location-issue-links button[data-issue="{issue}"]')).to_have_count(0)
    pune.locator('.location-issue-links button[data-issue="noncompliant"]').click()
    expect(page.locator('#locSource')).to_have_value('INTUNE')
    expect(page.locator('#locIssue')).to_have_value('noncompliant')
    expect(page.locator('#locSelection')).to_contain_text('1 matching records')
    expect(page.locator('#locDevices')).to_contain_text('NONCOMPLIANT-LAPTOP')
    expect(page.locator('#locDevices')).not_to_contain_text('SERVER')
    page.close()
