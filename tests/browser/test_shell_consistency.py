"""Keyboard and accessible naming across the portal shell."""
import pytest
from tests.browser.test_operator_queue import browser_context, expect

pytestmark = pytest.mark.browser


def test_infrastructure_subviews_work_by_keyboard(portal_url, browser_context):
    page = browser_context.new_page()
    page.goto(portal_url, wait_until='domcontentloaded')
    page.get_by_role('button', name='Infrastructure', exact=True).click()
    for name in ['networks', 'sites', 'servers', 'baseline']:
        control = page.locator(f'.category-card-tab[data-subtab="{name}"]')
        assert control.evaluate('(el) => el.tagName') == 'BUTTON'
        control.focus()
        page.keyboard.press('Enter')
        expect(control).to_have_attribute('aria-pressed', 'true')
        expect(page.locator(f'#subview-{name}')).to_be_visible()
    page.close()


def test_filter_names_and_same_origin_documentation(portal_url, browser_context):
    page = browser_context.new_page()
    page.goto(portal_url, wait_until='domcontentloaded')
    for name in ['FastAPI Docs','ReDoc']:
        url = page.get_by_role('link', name=name, exact=True).get_attribute('href')
        assert url.startswith('/')
        assert page.request.get(portal_url.rsplit('/', 1)[0] + url).status == 200
    for view, controls in [('infrastructure', ['swFilterHealth','swFilterStatus','swLocationSelect']),
                           ('endpoints',['epFilterStatus']),
                           ('cmdb',['cmdbFilterHealth','cmdbFilterSource','cmdbLocationSelect'])]:
        page.get_by_role('button', name={'infrastructure':'Infrastructure','endpoints':'Endpoints','cmdb':'CMDB'}[view], exact=True).click()
        for control in controls:
            assert page.locator(f'#{control}').get_attribute('aria-label')
    page.close()
