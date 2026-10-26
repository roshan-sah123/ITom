from pathlib import Path
import pytest
import pytest_asyncio
from tests.browser.test_operator_queue import browser_context, expect
from tests.browser.test_solarwinds_groups import group_inventory

pytestmark = pytest.mark.browser


@pytest_asyncio.fixture
async def approved_group(group_inventory,session):
    from app.services.group_location_service import GroupLocationService
    await GroupLocationService(session).approve(10,'pune','Fixture owner','Explicit correspondence verified in this isolated fixture')
    await session.commit()


def test_approved_combined_tree_uses_same_panel_and_scope(portal_url,approved_group,browser_context):
    page=browser_context.new_page();page.goto(portal_url,wait_until='networkidle')
    page.locator('.nav-tab[data-view="infrastructure"]').click()
    page.locator('.category-card-tab[data-subtab="sites"]').click()
    page.locator('#locMode').select_option('combined')
    page.locator('#swMappingToggle').click()
    page.locator('#swMappingFilter').select_option('approved')
    expect(page.locator('#swMappingRows tr')).to_have_count(1)
    expect(page.locator('#swMappingRows')).to_contain_text('Pune')
    expect(page.locator('#swMappingRows')).to_contain_text('50.0% · Red')
    page.locator('#swMappingFilter').select_option('scoreable')
    expect(page.locator('#swMappingRows tr')).to_have_count(1)
    page.locator('#swMappingToggle').click()
    page.locator('[data-group-path="10"] .sw-group-name').click()
    expect(page.locator('#swGroupSummary')).to_contain_text('Link: APPROVED · Pune')
    expect(page.locator('#swGroupSummary')).to_contain_text('50.0% · Red')
    expect(page.locator('#swGroupDevices tr')).to_have_count(2)
    page.locator('#swGroupSummary [data-category-index]').filter(has_text='Server').click()
    expect(page.locator('#swGroupDevices tr')).to_have_count(1)
    expect(page.locator('#swGroupSummary')).to_contain_text('50.0%')
    page.locator('#swGroupRefresh').click()
    expect(page.locator('#locMode')).to_have_value('combined')
    expect(page.locator('#swGroupSelection')).to_contain_text('Category: Server')
    page.locator('#swGroupResetDevices').click()
    expect(page.locator('#swGroupDevices tr')).to_have_count(2)
    page.close()


def test_home_labels_inline_scope_reload_and_responsive(portal_url, group_inventory, browser_context):
    page=browser_context.new_page()
    errors=[]; writes=[]
    page.on('pageerror',lambda error: errors.append(str(error)))
    page.on('request',lambda request: writes.append(request.url) if request.method != 'GET' else None)
    page.goto(portal_url,wait_until='networkidle')
    for route,label in [('home','Home page'),('infrastructure','Operations Analytics'),('endpoints','Digital Workspace'),('cmdb','Assets Analytics')]:
        expect(page.locator(f'.nav-tab[data-view="{route}"]')).to_have_text(label)
    expect(page.locator('#homeOverviewRows > tr[data-location]')).to_have_count(3)
    height=page.locator('.decision-kpi').first.bounding_box()['height']
    assert 180 <= height <= 270, height  # original desktop baseline 438px
    page.locator('#homeLocationSearch').fill('BOCBA')
    page.locator('#homeOverviewRows [data-open-group="10"]').click()
    expect(page.locator('#homeGroupDevices tr')).to_have_count(2)
    expect(page.locator('#homeGroupSummary')).to_contain_text('complete selected location')
    page.locator('#homeGroupSummary [data-category-index]').filter(has_text='Network').click()
    expect(page.locator('#homeGroupDevices tr')).to_have_count(1)
    expect(page.locator('#homeGroupDevices')).to_contain_text('Access Switch')
    page.locator('#homeGroupResetDevices').click()
    expect(page.locator('#homeGroupDevices tr')).to_have_count(2)
    page.locator('#homeGroupDeviceStatus').select_option('Critical')
    expect(page.locator('#homeGroupDevices tr')).to_have_count(1)
    page.locator('#overviewRefresh').click()
    expect(page.locator('#homeLocationSearch')).to_have_value('BOCBA')
    expect(page.locator('#homeGroupDeviceStatus')).to_have_value('Critical')
    expect(page.locator('#homeGroupDevices')).to_contain_text('Device 2')
    page.locator('#homeScoreMode').select_option('combined')
    expect(page.locator('#homeGroupSummary')).to_contain_text('approved Intune location link')
    expect(page.locator('#homeGroupDeviceStatus')).to_have_value('Critical')
    page.locator('#homeGroupBack').click()
    expect(page.locator('#homeOverviewRows [data-open-group="10"]')).to_be_focused()
    out=Path('output/playwright/dashboard-site-scores');out.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(out/'desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
    page.screenshot(path=str(out/'mobile.png'),full_page=True)
    page.locator('#globalSearch').fill('Device 2'); page.locator('#globalSearch').press('Enter')
    expect(page.locator('#view-cmdb')).to_be_visible()
    expect(page.locator('#cmdbSearchInput')).to_have_value('Device 2')
    assert writes==[] and errors==[]
    page.close()
