"""Operator-facing location priorities, disclosure and evidence explanations."""
from pathlib import Path
import re
from urllib.parse import urljoin

import pytest
import pytest_asyncio
from sqlalchemy import select
from app.models.ci import ConfigurationItem

from tests.browser.test_operator_queue import browser_context, expect

pytestmark = pytest.mark.browser


@pytest_asyncio.fixture
async def shutdown_inventory(operator_inventory, session):
    nodes = (await session.scalars(select(ConfigurationItem).where(
        ConfigurationItem.location_id == 'pune', ConfigurationItem.source_system == 'SOLARWINDS'
    ))).all()
    for node in nodes:
        node.status = 'Shutdown'
    await session.commit()


def test_unlinked_node_state_action_keeps_source_scope(portal_url, shutdown_inventory, browser_context):
    page = browser_context.new_page()
    open_scores(page, portal_url)
    pune = card(page, 'Pune')
    action = pune.locator('.location-primary-action')
    expect(action).to_have_attribute('data-issue', 'all')
    expect(action).to_have_attribute('data-source', 'SOLARWINDS')
    action.click()
    expect(page.locator('#locSource')).to_have_value('SOLARWINDS')
    expect(page.locator('#locIssue')).to_have_value('all')
    expect(page.locator('#locDevices tr')).to_have_count(2)
    expect(page.locator('#locDevices')).to_contain_text('Shutdown')
    expect(page.locator('#locDevices')).not_to_contain_text('LAPTOP')
    page.close()


def open_scores(page, portal_url):
    page.goto(portal_url, wait_until='domcontentloaded')
    page.locator('.nav-tab[data-view="infrastructure"]').click()
    page.locator('.category-card-tab[data-subtab="sites"]').click()
    page.locator('#locMode').select_option('auto')
    expect(page.locator('#locCards .location-score-card').first).to_be_visible(timeout=15000)


def card(page, name):
    return page.locator('.location-score-card').filter(has=page.get_by_role('button', name=name, exact=True))


def test_primary_action_filters_actual_inventory(portal_url, browser_context):
    page = browser_context.new_page()
    open_scores(page, portal_url)
    pune = card(page, 'Pune')
    expect(pune.locator('.location-card-attention.attention-health')).to_be_visible()
    expect(pune.locator('.location-main-reason')).not_to_be_empty()
    expect(pune.locator('.location-score-reason')).to_be_hidden()
    action = pune.locator('.location-primary-action')
    expect(action).to_have_count(1)
    selected_issue = action.get_attribute('data-issue')
    assert selected_issue == 'noncompliant'
    action.focus()
    page.keyboard.press('Enter')
    expect(page.locator('#locIssue')).to_have_value(selected_issue)
    expect(page.locator('#locSelection')).to_contain_text('1 matching records')
    expect(page.locator('#locDevices')).to_contain_text('NONCOMPLIANT-LAPTOP')
    expect(page.locator('#locDevices tr')).to_have_count(1)
    page.locator('#locClose').click()
    expect(action).to_be_focused()
    page.close()


def override_catalogue(page, portal_url, mutate):
    payload = page.request.get(urljoin(portal_url, '/api/v1/locations')).json()
    mutate(next(item for item in payload['data']['items'] if item['id'] == 'pune'))
    page.route('**/api/v1/locations', lambda route: route.fulfill(json=payload))


@pytest.mark.parametrize('problem', ['stale', 'mapping'])
def test_data_problem_has_evidence_or_mapping_action(portal_url, browser_context, problem):
    page = browser_context.new_page()

    def mutate(location):
        reason = 'Location identity needs review' if problem == 'mapping' else 'Source data is stale or unavailable'
        location['scores']['combined'] = dict(value=None, status='unavailable', reason=reason)
        if problem == 'mapping':
            location['issues']['conflict'] = 1
        else:
            location['freshness']['INTUNE']['status'] = 'STALE'
            for key in ['compliance', 'recent_checkins']:
                location['components'][key]['usable'] = False

    override_catalogue(page, portal_url, mutate)
    open_scores(page, portal_url)
    pune = card(page, 'Pune')
    expect(pune.locator('.location-card-attention.attention-data')).to_be_visible()
    action = pune.locator('.location-primary-action')
    expect(action).to_have_attribute('data-action', 'review' if problem == 'mapping' else 'refresh')
    if problem == 'mapping':
        action.click()
        expect(page.locator('#locationReviewPanel')).to_be_visible()
        expect(page.locator('#locBrowse')).to_be_hidden()
    else:
        with page.expect_response(lambda response: response.url.endswith('/api/v1/locations')):
            action.click()
        expect(page.locator('#locBrowse')).to_be_visible()
        expect(card(page, 'Pune').locator('.location-card-attention.attention-data')).to_be_visible()
    page.close()


@pytest.mark.parametrize('numerator,denominator,value,status,threshold', [
    (2249, 2500, 90.0, 'warning', '90'),
    (22499, 30000, 75.0, 'critical', '75'),
])
def test_rounded_boundary_explains_actual_colour(portal_url, browser_context, numerator, denominator, value, status, threshold):
    page = browser_context.new_page()

    def mutate(location):
        location['endpoints'] = 0
        location['nodes'] = denominator
        component = location['components']['node_status']
        component.update(numerator=numerator, denominator=denominator, value=round(100 * numerator / denominator, 2))
        location['scores']['infrastructure'] = dict(value=value, status=status, reason='A component is below 75%' if status == 'critical' else None)
        location['issues']['critical'] = 0
        location['issues']['down'] = denominator - numerator

    override_catalogue(page, portal_url, mutate)
    open_scores(page, portal_url)
    pune = card(page, 'Pune')
    expect(pune.locator('.location-score-value strong')).to_have_text(f'{value:.1f}')
    expect(pune.locator('.location-score-reason')).to_contain_text('below')
    expect(pune.locator('.location-score-reason')).to_contain_text(threshold)
    expect(pune.locator('.location-score-reason')).to_contain_text(re.compile('rounded', re.I))
    if status == 'critical':
        expect(pune.locator('.location-score-reason')).to_contain_text('22,499 / 30,000')
    else:
        expect(pune.locator('.location-score-reason')).to_contain_text('exact')
    page.close()


def test_high_average_keeps_component_override_visible(portal_url, browser_context):
    page = browser_context.new_page()

    def mutate(location):
        for key in ['compliance', 'recent_checkins']:
            location['components'][key].update(numerator=2, denominator=2, value=100)
        location['components']['node_status'].update(numerator=22499, denominator=30000, value=75.0)
        location['scores']['combined'] = dict(value=91.2, status='critical', reason='A component is below 75%')

    override_catalogue(page, portal_url, mutate)
    open_scores(page, portal_url)
    pune = card(page, 'Pune')
    expect(pune.locator('.location-score-value')).to_contain_text('Red')
    expect(pune.locator('.location-score-value strong')).to_have_text('91.2')
    expect(pune.locator('.location-score-reason')).to_be_visible()
    expect(pune.locator('.location-score-reason')).to_contain_text('22,499 / 30,000')
    expect(pune.locator('.location-score-reason')).to_contain_text('high average cannot override')
    page.close()


def test_other_issues_remain_available_without_adding_counts(portal_url, browser_context):
    page = browser_context.new_page()
    open_scores(page, portal_url)
    pune = card(page, 'Pune')
    expect(pune.locator('.location-main-reason')).not_to_contain_text('3 devices')
    pune.locator('details.location-card-details summary').first.click()
    for issue, expected in [('critical', 'CRITICAL-SERVER'), ('noncompliant', 'NONCOMPLIANT-LAPTOP'), ('old_checkins', 'NONCOMPLIANT-LAPTOP')]:
        pune.locator(f'.location-issue-links button[data-issue="{issue}"]').click()
        expect(page.locator('#locIssue')).to_have_value(issue)
        expect(page.locator('#locDevices')).to_contain_text(expected)
        expect(page.locator('#locDevices tr')).to_have_count(1)
        assert page.locator('#locIssue option').evaluate_all('(options) => options.map(option => option.value)') == [
            'all', 'noncompliant', 'other_compliance', 'old_checkins', 'old_30d', 'invalid_checkins',
            'up', 'down', 'critical', 'warning', 'unmanaged', 'conflict',
        ]
        page.locator('#locClose').click()
    page.close()


def test_healthy_disclosure_keyboard_mobile_and_comparison(portal_url, catalogue_inventory, browser_context):
    page = browser_context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    open_scores(page, portal_url)
    expect(page.locator('.location-comparison-note')).to_contain_text('same')
    page.locator('#locSearch').fill('Office 01')
    healthy = card(page, 'Office 01')
    expect(healthy.locator('.location-components')).to_be_hidden()
    expect(healthy.get_by_role('button', name='View devices for Office 01')).to_be_hidden()
    disclosure = healthy.locator('details.location-card-details')
    summary = disclosure.locator('summary').first
    summary.focus()
    page.keyboard.press('Enter')
    expect(healthy.locator('.location-components')).to_be_visible()
    expect(healthy.get_by_role('button', name='View devices for Office 01')).to_be_visible()
    page.keyboard.press('Enter')
    expect(healthy.locator('.location-components')).to_be_hidden()
    page.locator('#locMode').select_option('endpoints')
    expect(page.locator('#intuneLocationTree > li')).to_have_count(1)
    page.locator('[data-open-intune="office-1"]').click()
    expect(page.locator('#intuneSummary')).to_contain_text('Site Score · Intune')
    captures = Path('output/playwright/location-scorecard-clarity')
    captures.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(captures / 'healthy-desktop.png'), full_page=True)
    page.set_viewport_size({'width':390, 'height':844})
    page.locator('#intuneSummary details summary').click()
    expect(page.locator('#intuneSummary details')).to_have_attribute('open','')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
    page.screenshot(path=str(captures / 'healthy-mobile.png'), full_page=True)
    assert errors == []
    page.close()


def test_health_data_and_healthy_cards_on_desktop_mobile(portal_url, catalogue_inventory, browser_context):
    page = browser_context.new_page()
    payload = page.request.get(urljoin(portal_url, '/api/v1/locations')).json()
    payload['data']['items'] = [item for item in payload['data']['items'] if item['id'] in {'pune', 'noida', 'office-1', 'unassigned'}]
    noida = next(item for item in payload['data']['items'] if item['id'] == 'noida')
    noida['scores']['infrastructure'] = dict(value=None, status='unavailable', reason='Source data is stale or unavailable')
    noida['freshness']['SOLARWINDS']['status'] = 'STALE'
    noida['components']['node_status']['usable'] = False
    page.route('**/api/v1/locations', lambda route: route.fulfill(json=payload))
    open_scores(page, portal_url)
    expect(card(page, 'Pune').locator('.attention-health')).to_be_visible()
    expect(card(page, 'Noida').locator('.attention-data')).to_be_visible()
    expect(card(page, 'Office 01').locator('.location-components')).to_be_hidden()
    captures = Path('output/playwright/location-scorecard-clarity')
    captures.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(captures / 'cards-desktop.png'), full_page=True)
    page.set_viewport_size({'width':390, 'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
    page.screenshot(path=str(captures / 'cards-mobile.png'), full_page=True)
    page.close()
