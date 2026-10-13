"""Freshness and attempt outcomes remain separate, visible, and read-only."""
from pathlib import Path
import pytest
from tests.browser.test_operator_queue import browser_context, expect

pytestmark = pytest.mark.browser

REPORT = {
    'overall_status': 'STALE', 'oldest_age_seconds': 7200,
    'freshness_window_seconds': 1500,
    'sources': {
        'SOLARWINDS': {'status': 'STALE', 'age_seconds': 7200, 'last_synchronized_at': '2026-10-11T03:00:00Z'},
        'INTUNE': {'status': 'FRESH', 'age_seconds': 120, 'last_synchronized_at': '2026-10-11T04:58:00Z'},
    },
}
ATTEMPTS = {'solarwinds': {'status': 'FAILED'}, 'intune': {'status': 'PARTIAL'}}


@pytest.mark.parametrize('view,sources', [
    ('infrastructure', ['SOLARWINDS']), ('endpoints', ['INTUNE']), ('cmdb', ['SOLARWINDS', 'INTUNE']),
])
def test_workspace_source_evidence_and_reload(portal_url, browser_context, view, sources):
    page = browser_context.new_page()
    writes = []
    page.on('request', lambda request: writes.append(request.url) if request.method != 'GET' else None)
    page.route('**/api/v1/system/freshness', lambda route: route.fulfill(json=REPORT))
    page.route('**/api/v1/sync/status', lambda route: route.fulfill(json=ATTEMPTS))
    page.goto(portal_url, wait_until='domcontentloaded')
    expect(page.get_by_role('button', name='Reload snapshot', exact=True)).to_be_visible()
    expect(page.locator('#dataConfidence')).to_contain_text('SOLARWINDS latest refresh failed')
    page.locator(f'.nav-tab[data-view="{view}"]').click()
    panel = page.locator(f'#workspaceFreshness-{view}')
    for source in sources:
        row = panel.locator(f'[data-source="{source}"]')
        expect(row).to_have_attribute('data-status', REPORT['sources'][source]['status'].lower())
        expect(row).to_contain_text('Snapshot updated')
        expect(row).to_contain_text('Latest sync: ' + ATTEMPTS[source.lower()]['status'].lower())
        expect(row).to_contain_text('Showing last successful snapshot')
    assert panel.locator('[data-source]').count() == len(sources)
    panel.get_by_role('button', name='Reload snapshot', exact=True).click()
    expect(panel).not_to_contain_text('Checking source evidence')
    assert writes == []
    output = Path('outputs/workspace-freshness')
    output.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(output / f'{view}-desktop.png'))
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
    page.screenshot(path=str(output / f'{view}-mobile.png'))
    page.close()


def test_freshness_failure_and_unknown_are_distinct(portal_url, browser_context):
    page = browser_context.new_page()
    page.route('**/api/v1/system/freshness', lambda route: route.fulfill(status=503, body='{}'))
    page.goto(portal_url, wait_until='domcontentloaded')
    page.locator('.nav-tab[data-view="endpoints"]').click()
    panel = page.locator('#workspaceFreshness-endpoints')
    expect(panel).to_contain_text('Freshness unavailable')
    page.unroute('**/api/v1/system/freshness')
    page.route('**/api/v1/system/freshness', lambda route: route.fulfill(json={
        'sources': {'INTUNE': {'status': 'UNKNOWN', 'age_seconds': None, 'last_synchronized_at': None}},
    }))
    panel.get_by_role('button', name='Reload snapshot', exact=True).click()
    expect(panel).to_contain_text('No successful sync recorded')
    expect(panel).to_contain_text('Unknown')
    page.close()


def test_sync_status_failure_does_not_hide_freshness(portal_url, browser_context):
    page = browser_context.new_page()
    page.route('**/api/v1/system/freshness', lambda route: route.fulfill(json=REPORT))
    page.route('**/api/v1/sync/status', lambda route: route.fulfill(status=503, body='{}'))
    page.goto(portal_url, wait_until='domcontentloaded')
    page.locator('.nav-tab[data-view="endpoints"]').click()
    panel = page.locator('#workspaceFreshness-endpoints')
    expect(panel).to_contain_text('Fresh')
    expect(panel).to_contain_text('Snapshot updated')
    expect(panel).to_contain_text('Latest sync outcome unavailable')
    page.close()


def test_late_freshness_cannot_overwrite_reloaded_evidence(portal_url, browser_context):
    page = browser_context.new_page()
    page.goto(portal_url, wait_until='domcontentloaded')
    expect(page.locator('#attentionList button')).to_have_count(2)
    pending = []
    def evidence(route):
        if not pending:
            pending.append(route)
        else:
            route.fulfill(json=REPORT)
    page.route('**/api/v1/system/freshness', evidence)
    with page.expect_request('**/api/v1/system/freshness'):
        page.locator('.nav-tab[data-view="endpoints"]').click()
    page.locator('#brandHome').click()
    page.locator('.nav-tab[data-view="endpoints"]').click()
    panel = page.locator('#workspaceFreshness-endpoints')
    expect(panel).to_contain_text('Fresh')
    for route in pending:
        route.fulfill(json={'sources': {'INTUNE': {'status': 'UNKNOWN'}}})
    page.evaluate('() => new Promise(resolve => requestAnimationFrame(resolve))')
    expect(panel).to_contain_text('Snapshot updated')
    expect(panel).not_to_contain_text('No successful sync recorded')
    page.close()


def test_exception_inventory_keeps_source_evidence_visible(portal_url, browser_context):
    page = browser_context.new_page()
    page.route('**/api/v1/system/freshness', lambda route: route.fulfill(json=REPORT))
    page.route('**/api/v1/sync/status', lambda route: route.fulfill(json=ATTEMPTS))
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto(portal_url, wait_until='domcontentloaded')
    shortcut = page.locator('#attentionList button').filter(has_text='endpoints are noncompliant')
    expect(shortcut).to_be_visible()
    shortcut.click()
    evidence = page.locator('#inventoryFreshness-endpoints')
    expect(evidence).to_contain_text('partial')
    expect(evidence).to_be_in_viewport()
    output = Path('outputs/workspace-freshness')
    output.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(output / 'endpoint-exception-mobile.png'))
    page.close()


def test_reload_preserves_infrastructure_subtab(portal_url, browser_context):
    page = browser_context.new_page()
    page.goto(portal_url, wait_until='domcontentloaded')
    page.locator('.nav-tab[data-view="infrastructure"]').click()
    page.locator('.category-card-tab[data-subtab="networks"]').click()
    expect(page.locator('#subview-networks')).to_be_visible()
    panel = page.locator('#workspaceFreshness-infrastructure')
    panel.get_by_role('button', name='Reload snapshot', exact=True).click()
    expect(panel).not_to_contain_text('Checking source evidence')
    expect(page.locator('#subview-networks')).to_be_visible()
    expect(page.locator('#subview-servers')).to_be_hidden()
    page.close()
