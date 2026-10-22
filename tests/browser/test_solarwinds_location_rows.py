"""Canonical scorecards remain available beside the source-native group view."""
import pytest
import pytest_asyncio

from app.models.location import Location
from tests.factories import make_ci
from tests.browser.test_operator_queue import browser_context, expect
from tests.browser.test_location_scorecard_clarity import open_scores

pytestmark = pytest.mark.browser


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


@pytest.mark.parametrize('name,count', [('Green site',1), ('Amber site',5), ('Red site',2), ('Unknown site',1)])
def test_canonical_source_only_card_still_opens_its_devices(portal_url, solarwinds_locations, browser_context, name, count):
    page = browser_context.new_page()
    open_scores(page, portal_url)
    trigger = page.get_by_role('button', name=name, exact=True)
    trigger.focus(); page.keyboard.press('Enter')
    expect(page.locator('#locDetailTitle')).to_have_text(f'{name} inventory')
    expect(page.locator('#locDevices tr')).to_have_count(count)
    page.locator('#locClose').click()
    expect(trigger).to_be_focused()
    page.close()


def test_combined_catalogue_keeps_source_filtered_export(portal_url, browser_context):
    page = browser_context.new_page()
    open_scores(page, portal_url)
    page.get_by_role('button', name='Pune', exact=True).click()
    expect(page.locator('#locDevices tr')).to_have_count(4)
    page.locator('#locSource').select_option('SOLARWINDS')
    expect(page.locator('#locDevices tr')).to_have_count(2)
    with page.expect_download() as captured:
        page.locator('#locExport').click()
    with open(captured.value.path(), encoding='utf-8-sig') as exported:
        csv = exported.read()
        assert 'CRITICAL-SERVER' in csv and 'HEALTHY-SERVER' in csv and 'LAPTOP' not in csv
    page.close()
