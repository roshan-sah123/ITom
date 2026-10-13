"""Review a mapping through the actual local UI, API and database."""
from pathlib import Path
from urllib.parse import urljoin
import pytest
import pytest_asyncio
from sqlalchemy import select
from app.models.location import LocationMappingRule
from app.models.ci import ConfigurationItem
from tests.browser.test_operator_queue import browser_context, expect

pytestmark=pytest.mark.browser


@pytest_asyncio.fixture
async def review_inventory(operator_inventory,session):
    rule=LocationMappingRule(id='review-prefix',source_system='INTUNE',match_key='NONCOMPLIANT-',
                            location_id='pune',revision='a'*64,enabled=True,approval_status='PENDING',
                            review_note='Source owner needs to verify this prefix')
    session.add(rule);await session.flush()
    ci=(await session.scalars(select(ConfigurationItem).where(ConfigurationItem.name=='NONCOMPLIANT-LAPTOP'))).one()
    ci.location_rule_id=rule.id;ci.location_resolution='review';ci.location_revision='pending'
    await session.commit()


def test_location_review_approval_and_history(portal_url,review_inventory,browser_context):
    page=browser_context.new_page()
    page.goto(portal_url,wait_until='domcontentloaded')
    page.locator('.nav-tab[data-view="infrastructure"]').click()
    page.locator('.category-card-tab[data-subtab="sites"]').click()
    page.get_by_role('button',name='Review location mappings',exact=True).click()
    expect(page.locator('#locationReviewPanel')).to_be_visible()
    expect(page.locator('#reviewRules')).to_contain_text('NONCOMPLIANT-')
    page.locator('#reviewRules button').click()
    page.locator('#reviewDecision').select_option('APPROVED')
    page.locator('#reviewReviewer').fill('Test site owner')
    page.locator('#reviewComment').fill('Verified with location owner')
    page.get_by_role('button',name='Save review',exact=True).click()
    expect(page.locator('#reviewMessage')).to_contain_text('Approved',timeout=15000)
    expect(page.locator('#reviewLastDecision')).to_contain_text('Test site owner')
    page.locator('#reviewStatus').select_option('APPROVED')
    expect(page.locator('#reviewRules')).to_contain_text('Test site owner')
    expect(page.locator('#reviewHistory')).to_contain_text('PENDING → APPROVED')
    result=page.request.get(urljoin(portal_url,'/api/v1/locations/pune/devices?issue=noncompliant')).json()['data']
    assert result['items'][0]['location_resolution']=='mapped'
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
    captures=Path('outputs/location-review-tests');captures.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(captures/'review-mobile.png'),full_page=True)
    page.locator('#reviewClose').click()
    expect(page.locator('#locBrowse')).to_be_visible()
    page.close()
