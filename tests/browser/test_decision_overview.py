"""Evidence and unavailable-state contracts for decision overview."""
import pytest
from pathlib import Path
from tests.browser.test_operator_queue import browser_context, expect

pytestmark = pytest.mark.browser


def test_decision_overview_separates_evidence_and_actions(portal_url, browser_context):
    page = browser_context.new_page()
    page.goto(portal_url, wait_until='domcontentloaded')
    expect(page.locator('#decisionCompliance')).to_contain_text('33.3%', timeout=15000)
    expect(page.locator('#decisionComplianceEvidence')).to_contain_text('1 / 3')
    expect(page.locator('#decisionAvailabilityEvidence')).to_contain_text('1 / 3')
    expect(page.locator('#decisionPressure')).to_have_text('Unavailable')
    expect(page.locator('#dataConfidence')).to_contain_text('compliance')
    expect(page.locator('#overviewRisk')).to_have_count(0)
    expect(page.locator('#attentionList')).not_to_contain_text('Source data is stale')
    captures = Path('output/playwright')
    captures.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(captures / 'decision-overview-desktop.png'), full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
    page.screenshot(path=str(captures / 'decision-overview-mobile.png'), full_page=True)
    page.close()


def test_summary_failure_overrides_fresh_source_status(portal_url, browser_context):
    page = browser_context.new_page()
    page.route('**/api/v1/intune/summary', lambda route: route.fulfill(status=503, body='{}'))
    page.goto(portal_url, wait_until='domcontentloaded')
    expect(page.locator('#overviewFreshness')).to_contain_text('UNAVAILABLE', timeout=15000)
    expect(page.locator('#decisionCompliance')).to_have_text('Unavailable')
    expect(page.locator('#decisionComplianceFreshness')).to_contain_text('Unavailable')
    expect(page.locator('#attentionList')).not_to_contain_text('No active exceptions')
    expect(page.locator('#sourceList')).to_contain_text('UNAVAILABLE')
    expect(page.locator('#dataConfidence')).to_contain_text('Microsoft Intune summary unavailable')
    page.close()


def test_cards_expose_source_freshness_and_partial_resource_coverage(portal_url, browser_context):
    page = browser_context.new_page()
    page.route('**/api/v1/system/freshness', lambda route: route.fulfill(json={
        'overall_status':'STALE','oldest_age_seconds':3600,'sources':{
            'INTUNE':{'status':'FRESH','age_seconds':60,'last_synchronized_at':'2026-10-12T05:30:00Z'},
            'SOLARWINDS':{'status':'STALE','age_seconds':3600,'last_synchronized_at':'2026-10-12T04:30:00Z'}}}))
    page.route('**/api/v1/solarwinds/summary', lambda route: route.fulfill(json={
        'metrics':{'total_nodes':1625,'low_critical_nodes':35},'decision_metrics':{
            'current_node_status':{'value':93.5,'numerator':1485,'denominator':1589,'unknown_count':0},
            'resource_pressure':{'value':2.15,'numerator':35,'denominator':1625,'known_count':856,'unknown_count':769,'coverage_pct':52.68}}}))
    page.goto(portal_url,wait_until='domcontentloaded')
    expect(page.get_by_role('heading',name='Endpoint compliance',exact=True)).to_be_visible()
    expect(page.get_by_role('heading',name='Nodes reporting Up',exact=True)).to_be_visible()
    expect(page.get_by_role('heading',name='Nodes above CPU / memory thresholds',exact=True)).to_be_visible()
    expect(page.locator('#decisionComplianceFreshness')).to_contain_text('Intune · Fresh')
    expect(page.locator('#decisionAvailabilityFreshness')).to_contain_text('SolarWinds · Stale')
    expect(page.locator('#decisionAvailabilityFreshness')).to_contain_text('Last successful refresh:')
    expect(page.locator('#decisionAvailabilityFreshness')).to_contain_text('Showing an older snapshot')
    expect(page.locator('#decisionPressure')).to_contain_text('2.1%')
    expect(page.locator('#decisionPressureCoverage')).to_contain_text('Limited coverage · 52.7%')
    expect(page.locator('#decisionPressureCoverage')).to_contain_text('856 / 1,625')
    expect(page.locator('#decisionPressureCoverage')).to_contain_text('may hide additional')
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
    page.close()


def test_freshness_failure_never_labels_cards_fresh(portal_url, browser_context):
    page = browser_context.new_page()
    page.route('**/api/v1/system/freshness',lambda route: route.fulfill(status=503,body='{}'))
    page.goto(portal_url,wait_until='domcontentloaded')
    expect(page.locator('#decisionComplianceFreshness')).to_contain_text('Freshness unavailable')
    expect(page.locator('#decisionAvailabilityFreshness')).to_contain_text('Freshness unavailable')
    page.close()


def test_empty_population_never_becomes_zero_percent(portal_url, browser_context):
    page = browser_context.new_page()
    page.route('**/api/v1/intune/summary', lambda route: route.fulfill(json={
        'metrics':{'total_managed_devices':0,'noncompliant_devices':0},
        'decision_metrics':{'confirmed_compliance':{'value':None,'numerator':0,'denominator':0,'unknown_count':0}}
    }))
    page.goto(portal_url, wait_until='domcontentloaded')
    expect(page.locator('#decisionCompliance')).to_have_text('No population', timeout=15000)
    expect(page.locator('#decisionComplianceEvidence')).to_contain_text('0 / 0')
    page.close()


def test_cmdb_unavailable_body_is_not_a_healthy_zero(portal_url, browser_context):
    page = browser_context.new_page()
    page.route('**/api/v1/cmdb/summary', lambda route: route.fulfill(json={'total_cis':0, 'data_available':False}))
    page.goto(portal_url, wait_until='domcontentloaded')
    expect(page.locator('#overviewCis')).to_have_text('Unavailable', timeout=15000)
    expect(page.locator('#overviewFreshness')).to_contain_text('UNAVAILABLE')
    expect(page.locator('#dataConfidence')).to_contain_text('CMDB summary unavailable')
    page.close()
