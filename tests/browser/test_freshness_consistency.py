"""Snapshot ages advance without fetching evidence for unloaded inventory."""
import pytest
from tests.browser.test_operator_queue import browser_context, expect
from tests.browser.test_workspace_freshness import REPORT, ATTEMPTS

pytestmark = pytest.mark.browser


def test_loaded_snapshot_age_advances_without_replacing_evidence(portal_url, browser_context):
    page = browser_context.new_page()
    page.clock.install()
    page.route('**/api/v1/system/freshness', lambda route: route.fulfill(json=REPORT))
    page.route('**/api/v1/sync/status', lambda route: route.fulfill(json=ATTEMPTS))
    page.goto(portal_url, wait_until='domcontentloaded')
    page.locator('.nav-tab[data-view="endpoints"]').click()
    panel = page.locator('#workspaceFreshness-endpoints')
    expect(panel).to_contain_text('2m old')
    # The global header polls independently; newer source metadata must not
    # replace the evidence belonging to this loaded workspace snapshot.
    page.unroute('**/api/v1/system/freshness')
    page.route('**/api/v1/system/freshness', lambda route: route.fulfill(json={
        'sources': {'INTUNE': {'status': 'UNKNOWN', 'age_seconds': None}},
    }))
    page.clock.fast_forward(120000)
    expect(panel).to_contain_text('4m old')
    expect(page.locator('#inventoryFreshness-endpoints')).to_contain_text('4m old')
    expect(panel).to_contain_text('Fresh at load')
    expect(panel).to_contain_text('Freshness checked at')
    expect(panel).not_to_contain_text('No successful sync recorded')
    page.close()


def test_navigation_clears_previous_snapshot_age_timer(portal_url, browser_context):
    page = browser_context.new_page()
    page.clock.install()
    page.route('**/api/v1/system/freshness', lambda route: route.fulfill(json=REPORT))
    page.route('**/api/v1/sync/status', lambda route: route.fulfill(json=ATTEMPTS))
    page.goto(portal_url, wait_until='domcontentloaded')
    page.locator('.nav-tab[data-view="endpoints"]').click()
    panel = page.locator('#workspaceFreshness-endpoints')
    expect(panel).to_contain_text('2m old')
    page.locator('#brandHome').click()
    page.clock.fast_forward(120000)
    expect(panel).to_contain_text('2m old')
    page.close()
