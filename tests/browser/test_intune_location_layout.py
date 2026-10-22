from pathlib import Path
import pytest
from tests.browser.test_operator_queue import browser_context,expect

pytestmark=pytest.mark.browser


def open_intune(page,url):
    page.goto(url,wait_until='domcontentloaded')
    page.locator('.nav-tab[data-view="infrastructure"]').click()
    page.locator('.category-card-tab[data-subtab="sites"]').click()
    page.locator('#locMode').select_option('endpoints')
    expect(page.locator('#intuneLocationTree')).to_be_visible()


def test_shared_location_layout_tiles_filters_reload_drawer_and_focus(portal_url,browser_context):
    page=browser_context.new_page();errors=[];writes=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.on('request',lambda request:writes.append(request.url) if request.method!='GET' else None)
    open_intune(page,portal_url)
    expect(page.locator('#intuneLocationTree > li')).to_have_count(1)
    expect(page.locator('#intuneCoverage')).to_contain_text('2 / 3')
    trigger=page.locator('[data-open-intune="pune"]');trigger.press('Enter')
    expect(page.locator('#intuneDevices tr')).to_have_count(2)
    expect(page.locator('#intuneSummary')).to_contain_text('Site Score · Intune')
    expect(page.locator('#intuneSummary')).not_to_contain_text('SolarWinds health')
    expect(page.locator('#intuneSummary')).to_contain_text('50.0% · Red')
    page.locator('[data-intune-issue="noncompliant"]').click()
    expect(page.locator('#intuneDevices tr')).to_have_count(1)
    expect(page.locator('#intuneDevices')).to_contain_text('NONCOMPLIANT-LAPTOP')
    expect(page.locator('#intuneDevices')).not_to_contain_text('SERVER')
    expect(page.locator('#intuneSummary')).to_contain_text('50.0% · Red')
    page.locator('#intuneRefresh').click()
    expect(page.locator('#locMode')).to_have_value('endpoints')
    expect(page.locator('#intuneSelection')).to_contain_text('Noncompliant')
    page.locator('#intuneResetDevices').click()
    expect(page.locator('#intuneDevices tr')).to_have_count(2)
    page.locator('[data-intune-issue="compliant"]').click()
    expect(page.locator('#intuneDevices')).to_contain_text('COMPLIANT-LAPTOP')
    expect(page.locator('#intuneDevices')).not_to_contain_text('NONCOMPLIANT-LAPTOP')
    page.locator('#intuneDevices [data-ci]').click()
    expect(page.locator('#slideDrawer')).to_be_visible();page.keyboard.press('Escape')
    expect(page.locator('#intuneDevices [data-ci]')).to_be_focused()
    page.locator('#intuneClose').click();expect(trigger).to_be_focused()
    page.locator('#intuneUnassigned').click()
    expect(page.locator('#intuneDevices')).to_contain_text('UNASSIGNED-LAPTOP')
    expect(page.locator('#intuneSummary')).to_contain_text('Unavailable')
    page.locator('#intuneClose').click()
    trigger.click()
    out=Path('output/playwright/intune-location-layout');out.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(out/'desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
    page.screenshot(path=str(out/'mobile.png'),full_page=True)
    page.locator('#locMode').select_option('infrastructure')
    expect(page.locator('#swGroupTree')).to_be_visible()
    assert not errors and not writes
    page.close()


def test_intune_errors_retry_and_location_filter_retention(portal_url,browser_context):
    page=browser_context.new_page()
    page.route('**/api/v1/locations',lambda route:route.fulfill(status=503,json={'detail':'Unavailable'}))
    open_intune(page,portal_url)
    expect(page.locator('#intuneMessage')).to_contain_text('unavailable')
    page.unroute('**/api/v1/locations');page.locator('#intuneRetry').click()
    expect(page.locator('[data-open-intune="pune"]')).to_be_visible()
    page.locator('#locSearch').fill('Pune');page.locator('#locStatus').select_option('critical')
    page.route('**/api/v1/locations/pune/score',lambda route:route.fulfill(status=503,json={'detail':'Unavailable'}))
    page.locator('[data-toggle-intune="pune"]').click()
    expect(page.locator('#intuneSummary')).to_contain_text('unavailable')
    page.unroute('**/api/v1/locations/pune/score');page.locator('#intuneRetrySummary').click()
    expect(page.locator('#intuneDevices tr')).to_have_count(2)
    page.locator('[data-intune-issue="recent_checkins"]').click()
    expect(page.locator('#intuneDevices tr')).to_have_count(1)
    expect(page.locator('#intuneDevices')).to_contain_text('COMPLIANT-LAPTOP')
    page.locator('#intuneRefresh').click()
    expect(page.locator('#locSearch')).to_have_value('Pune')
    expect(page.locator('#locStatus')).to_have_value('critical')
    expect(page.locator('#intuneIssue')).to_have_value('recent_checkins')
    expect(page.locator('#intuneDevices tr')).to_have_count(1)
    page.close()
