"""Exception journeys land on loaded evidence without waiting for analytics."""
import pytest
from pathlib import Path

from tests.browser.test_operator_queue import browser_context, expect

pytestmark = pytest.mark.browser

WORKSPACES = [
    ('infrastructure', 'SolarWinds nodes need review', 'sw', 'CRITICAL-SERVER',
     'solarwinds/nodes', 'solarwinds/summary'),
    ('endpoints', 'endpoints are noncompliant', 'ep', 'NONCOMPLIANT-LAPTOP',
     'intune/devices', 'intune/summary'),
]


def open_overview(page, portal_url, queue_label):
    page.goto(portal_url, wait_until='domcontentloaded')
    shortcut = page.locator('#attentionList button.attention-item').filter(has_text=queue_label)
    expect(shortcut).to_be_visible(timeout=15000)
    return shortcut


@pytest.mark.parametrize('workspace,label,prefix,name,grid,summary', WORKSPACES)
def test_exception_lands_on_inventory_and_charts_remain_optional(
        portal_url, browser_context, workspace, label, prefix, name, grid, summary):
    page = browser_context.new_page()
    shortcut = open_overview(page, portal_url, label)
    shortcut.click()
    heading = page.locator(f'#{prefix}InventoryHeading')
    expect(heading).to_be_focused()
    expect(page.get_by_role('button', name=name, exact=True)).to_be_visible()
    chart_summary = page.locator(f'#{prefix}ChartSummary')
    expect(chart_summary).not_to_have_attribute('open', '')
    assert 0 <= heading.bounding_box()['y'] < page.viewport_size['height']
    output = Path('outputs/exception-investigation')
    output.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(output / f'{workspace}-desktop.png'))
    page.set_viewport_size({'width': 390, 'height': 844})
    page.locator('#brandHome').click()
    shortcut = page.locator('#attentionList button.attention-item').filter(has_text=label)
    expect(shortcut).to_be_visible()
    shortcut.click()
    expect(heading).to_be_focused()
    expect(heading).to_be_in_viewport()
    expect(page.get_by_role('button', name=name, exact=True)).to_be_in_viewport()
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 2')
    page.screenshot(path=str(output / f'{workspace}-mobile.png'))
    page.set_viewport_size({'width': 1440, 'height': 900})

    # Native disclosure must remain keyboard operable and retain inventory state.
    chart_summary.locator('summary').press('Enter')
    expect(chart_summary).to_have_attribute('open', '')
    chart_summary.locator('summary').press('Enter')
    expect(chart_summary).not_to_have_attribute('open', '')
    page.get_by_role('button', name=name, exact=True).click()
    expect(page.locator('#slideDrawer')).to_be_visible()
    page.keyboard.press('Escape')
    page.locator(f'#{prefix}ClearActiveFilterBtn').click()
    expect(page.locator(f'#{prefix}ActiveFilterBanner')).to_be_hidden()
    page.close()


@pytest.mark.parametrize('workspace,label,prefix,name,grid,summary', WORKSPACES)
def test_slow_analytics_does_not_delay_exception_inventory(
        portal_url, browser_context, workspace, label, prefix, name, grid, summary):
    page = browser_context.new_page()
    shortcut = open_overview(page, portal_url, label)
    pending = []
    page.route(f'**/api/v1/{summary}', lambda route: pending.append(route))
    shortcut.click()
    expect(page.get_by_role('button', name=name, exact=True)).to_be_visible()
    expect(page.locator(f'#{prefix}InventoryHeading')).to_be_focused()
    assert pending, 'Analytics request must still be pending when evidence receives focus'
    for route in pending:
        route.abort()
    expect(page.locator('#epTotalVal' if prefix == 'ep' else '#swTotalNodesVal')).to_have_text('Unavailable')
    # Failure of optional analytics must not erase the loaded drawer's row cache.
    page.get_by_role('button', name=name, exact=True).click()
    expect(page.locator('#slideDrawer')).to_be_visible()
    expect(page.locator('#drawerContent')).to_contain_text(name)
    page.close()


@pytest.mark.parametrize('workspace,label,prefix,name,grid,summary', WORKSPACES)
def test_late_inventory_does_not_steal_focus_after_navigation(
        portal_url, browser_context, workspace, label, prefix, name, grid, summary):
    page = browser_context.new_page()
    shortcut = open_overview(page, portal_url, label)
    pending = []
    page.route(f'**/api/v1/{grid}?*', lambda route: pending.append(route))
    with page.expect_request(f'**/api/v1/{grid}?*'):
        shortcut.click()
    # An unfinished table must not be announced as the investigation destination.
    expect(page.locator(f'#{prefix}InventoryHeading')).not_to_be_focused()
    page.locator('#brandHome').click()
    expect(page.locator('#view-home')).to_be_visible()
    assert pending
    for route in pending:
        route.continue_()
    expect(page.get_by_role('button', name=name, exact=True, include_hidden=True)).to_be_attached()
    page.evaluate('() => new Promise(resolve => requestAnimationFrame(resolve))')
    expect(page.locator(f'#{prefix}InventoryHeading')).not_to_be_focused()
    expect(page.locator('#brandHome')).to_be_focused()
    page.close()


@pytest.mark.parametrize('workspace,label,prefix,name,grid,summary', WORKSPACES)
def test_normal_navigation_keeps_summary_available(
        portal_url, browser_context, workspace, label, prefix, name, grid, summary):
    page = browser_context.new_page()
    open_overview(page, portal_url, label)
    page.locator(f'.nav-tab[data-view="{workspace}"]').click()
    expect(page.get_by_role('button', name=name, exact=True)).to_be_visible()
    expect(page.locator(f'#{prefix}ChartSummary')).to_have_attribute('open', '')
    expect(page.locator(f'#{prefix}InventoryHeading')).not_to_be_focused()
    page.close()


def test_server_exception_returns_from_another_infrastructure_subtab(portal_url, browser_context):
    page = browser_context.new_page()
    open_overview(page, portal_url, 'SolarWinds nodes need review')
    page.locator('.nav-tab[data-view="infrastructure"]').click()
    page.locator('.category-card-tab[data-subtab="sites"]').click()
    expect(page.locator('#subview-sites')).to_be_visible()
    page.locator('#brandHome').click()
    shortcut = page.locator('#attentionList button.attention-item').filter(has_text='SolarWinds nodes need review')
    expect(shortcut).to_be_visible()
    shortcut.click()
    expect(page.locator('#subview-servers')).to_be_visible()
    expect(page.locator('#swInventoryHeading')).to_be_focused()
    page.close()
