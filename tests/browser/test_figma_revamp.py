"""The exported frontend reads real isolated API data and preserves failure states."""
import csv
from pathlib import Path

import pytest
from tests.factories import make_ci

expect = pytest.importorskip('playwright.sync_api').expect

pytestmark = pytest.mark.browser


@pytest.fixture
async def drilldown_url(revamp_portal_url, session):
    session.add_all([
        make_ci('SOLARWINDS', f'EXTRA-SERVER-{index:02}', 'Up', 'Low' if index == 0 else 'High',
                attributes={'node_category':'Server','cpu_load':95 if index==0 else 10,'memory_used':20})
        for index in range(12)
    ] + [make_ci('INTUNE','MAC-ENDPOINT','Compliant','High',ci_type='macOS',vendor='Apple')])
    await session.commit()
    return revamp_portal_url


def test_summary_and_chart_clicks_filter_reset_paginate_and_export(drilldown_url, browser_context):
    page=browser_context.new_page()
    page.goto(drilldown_url)
    page.get_by_role('button',name='Operations Analytics',exact=True).click()
    page.get_by_role('button',name='View Classified servers',exact=True).click()
    expect(page.get_by_label('Source category')).to_have_value('Server')
    expect(page.locator('.inventory-panel .table-footer')).to_contain_text('of 14 records')
    page.get_by_label('Rows per page').select_option('10')
    expect(page.locator('tbody tr')).to_have_count(10)
    page.get_by_role('button',name='Next',exact=True).click()
    expect(page.locator('tbody tr')).to_have_count(4)
    page.get_by_role('button',name='Filter Health classification: Low',exact=True).click()
    expect(page.get_by_label('Health tier')).to_have_value('Low')
    expect(page.get_by_label('Source category')).to_have_value('')
    expect(page.locator('tbody tr')).to_have_count(3)
    page.get_by_role('button',name='Filter Operational status: Down',exact=True).click()
    expect(page.get_by_label('Filter status')).to_have_value('Down')
    expect(page.get_by_label('Health tier')).to_have_value('')
    expect(page.locator('tbody tr')).to_have_count(1)
    expect(page.locator('tbody')).to_contain_text('DOWN-SWITCH')
    page.get_by_role('searchbox',name='Search SolarWinds node inventory').fill('no-such-node')
    expect(page.locator('.empty-state')).to_contain_text('No records match')
    page.get_by_role('button',name='View Network infrastructure',exact=True).click()
    expect(page.get_by_label('Source category')).to_have_value('Network')
    expect(page.get_by_role('searchbox',name='Search SolarWinds node inventory')).to_have_value('')
    expect(page.locator('tbody tr')).to_have_count(1)
    with page.expect_download() as download:
        page.get_by_role('button',name='Export CSV',exact=True).click()
    rows=list(csv.DictReader(Path(download.value.path()).read_text(encoding='utf-8-sig').splitlines()))
    assert len(rows)==1 and rows[0]['Node name']=='DOWN-SWITCH'
    page.get_by_role('button',name='Clear filters',exact=True).click()
    expect(page.locator('.inventory-panel .table-footer')).to_contain_text('of 15 records')
    page.close()


def test_group_card_and_endpoint_asset_charts_open_matching_data(revamp_groups_url,browser_context):
    page=browser_context.new_page()
    page.goto(revamp_groups_url)
    page.get_by_role('button',name='Operations Analytics',exact=True).click()
    page.get_by_role('button',name='View Location health',exact=True).click()
    expect(page.get_by_role('heading',name='SolarWinds location groups',exact=True)).to_be_visible()
    page.get_by_role('button',name='View group BOCBA(Bolivia,Cochabamba-Encora)',exact=True).click()
    expect(page.locator('.inventory-panel .table-footer')).to_contain_text('of 2 records')
    page.get_by_role('button',name='Clear filters',exact=True).click()
    expect(page.locator('.inventory-panel .table-footer')).to_contain_text('of 5 records')
    page.get_by_role('button',name='Digital Workspace',exact=True).click()
    page.get_by_role('button',name='Filter Operating system fleet: Windows',exact=True).click()
    expect(page.locator('.inventory-panel .table-footer')).to_contain_text('of 3 records')
    page.get_by_role('button',name='Filter Device compliance policy: NonCompliant',exact=True).click()
    expect(page.locator('tbody tr')).to_have_count(1)
    expect(page.locator('tbody')).to_contain_text('NONCOMPLIANT-LAPTOP')
    page.get_by_role('button',name='Assets Analytics',exact=True).click()
    page.get_by_role('button',name='Filter Records by source: Microsoft Intune',exact=True).click()
    expect(page.get_by_label('Source system', exact=True)).to_have_value('INTUNE')
    expect(page.locator('.inventory-panel .table-footer')).to_contain_text('of 3 records')
    page.close()


def test_selected_card_refreshes_current_rows_without_losing_filter(drilldown_url, browser_context):
    page = browser_context.new_page()
    page.clock.install()
    page.goto(drilldown_url)
    page.get_by_role('button', name='Operations Analytics', exact=True).click()
    page.get_by_role('button', name='View Classified servers', exact=True).press('Enter')
    expect(page.locator('.inventory-panel .table-footer')).to_contain_text('of 14 records')

    def updated_inventory(route):
        response = route.fetch()
        data = response.json()
        row = {**data['items'][0], 'id': '00000000-0000-0000-0000-000000000001', 'name': 'UPDATED-SERVER'}
        data['items'].append(row)
        data['total'] += 1
        route.fulfill(response=response, json=data)

    def updated_summary(route):
        response = route.fetch()
        data = response.json()
        data['metrics']['server_nodes_count'] += 1
        data['metrics']['total_nodes'] += 1
        route.fulfill(response=response, json=data)

    page.route('**/api/v1/solarwinds/nodes?*category=Server*', updated_inventory)
    page.route('**/api/v1/solarwinds/summary', updated_summary)
    page.clock.fast_forward(60_000)
    expect(page.get_by_label('Source category')).to_have_value('Server')
    expect(page.locator('.inventory-panel .table-footer')).to_contain_text('of 15 records')
    expect(page.locator('tbody')).to_contain_text('UPDATED-SERVER')
    expect(page.get_by_role('button', name='View Classified servers', exact=True)).to_contain_text('15')
    page.get_by_role('button', name='Reload snapshot', exact=True).click()
    expect(page.get_by_label('Source category')).to_have_value('Server')
    expect(page.locator('.inventory-panel .table-footer')).to_contain_text('of 15 records')
    page.close()


def test_only_current_ui_navigation_is_exposed(revamp_portal_url, browser_context):
    page = browser_context.new_page()
    page.goto(revamp_portal_url)
    expect(page.get_by_role('heading', name='Operations overview')).to_be_visible()
    expect(page.get_by_role('link', name='Existing portal')).to_have_count(0)
    expect(page.get_by_role('button', name='Open existing portal')).to_have_count(0)
    page.get_by_role('button', name='Open Knowledge Center', exact=True).click()
    expect(page.get_by_role('heading', name='Knowledge Center', exact=True)).to_be_visible()
    page.get_by_role('button', name='Help & support', exact=True).click()
    expect(page.get_by_role('heading', name='Knowledge Center', exact=True)).to_be_visible()
    page.close()


@pytest.fixture
async def revamp_inventory_url(revamp_portal_url, session):
    session.add_all([
        make_ci('INTUNE', f'NOIDA-EXPORT-{i:02}', 'Compliant', 'High',
                location_id='noida', location_resolution='mapped')
        for i in range(12)
    ])
    await session.commit()
    return revamp_portal_url


def test_inventory_filters_pagination_complete_csv_and_details(revamp_inventory_url, browser_context):
    page = browser_context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(revamp_inventory_url)
    page.get_by_role('button', name='Digital Workspace', exact=True).click()
    expect(page.get_by_role('heading', name='Digital employee experience')).to_be_visible()
    expect(page.locator('tbody tr')).to_have_count(15)
    page.get_by_label('Reporting location').select_option('noida')
    page.get_by_label('Rows per page').select_option('10')
    expect(page.locator('tbody tr')).to_have_count(10)
    expect(page.locator('.table-footer')).to_contain_text('of 12 records')
    page.get_by_role('button', name='Next', exact=True).click()
    expect(page.locator('tbody tr')).to_have_count(2)
    with page.expect_download() as download:
        page.get_by_role('button', name='Export CSV').click()
    rows = list(csv.DictReader(Path(download.value.path()).read_text(encoding='utf-8-sig').splitlines()))
    assert len(rows) == 12
    assert {row['Reporting location'] for row in rows} == {'Noida'}
    page.get_by_label('Reporting location').select_option('pune')
    page.get_by_label('Filter status').select_option('NonCompliant')
    expect(page.locator('tbody tr')).to_have_count(1)
    expect(page.locator('tbody')).to_contain_text('NONCOMPLIANT-LAPTOP')
    trigger = page.get_by_role('button', name='Inspect NONCOMPLIANT-LAPTOP', exact=True)
    trigger.click()
    expect(page.get_by_role('dialog')).to_be_visible()
    expect(page.get_by_role('dialog')).to_contain_text('Last synchronized')
    expect(page.get_by_role('dialog')).to_contain_text('No status changes recorded')
    page.keyboard.press('Escape')
    expect(page.get_by_role('dialog')).to_have_count(0)
    expect(trigger).to_be_focused()
    assert not errors
    page.close()


def test_errors_empty_recovery_and_unsupported_workspaces(revamp_portal_url, browser_context):
    page = browser_context.new_page()
    page.route('**/api/v1/intune/devices?*', lambda route: route.fulfill(status=503, json={'error': 'Unavailable'}))
    page.goto(revamp_portal_url)
    page.get_by_role('button', name='Digital Workspace', exact=True).click()
    expect(page.get_by_role('alert')).to_contain_text('Data unavailable (HTTP 503)')
    expect(page.locator('.empty-state')).not_to_contain_text('No records match')
    page.unroute('**/api/v1/intune/devices?*')
    page.get_by_role('button', name='Retry', exact=True).click()
    expect(page.locator('tbody tr')).to_have_count(3)
    page.get_by_role('searchbox', name='Search Managed endpoint inventory').fill('absent-device')
    expect(page.locator('.empty-state')).to_contain_text('No records match')
    page.get_by_role('button', name='Knowledge Center', exact=True).click()
    expect(page.get_by_role('heading', name='Data service unavailable')).to_be_visible()
    expect(page.locator('main')).not_to_contain_text('248')
    page.get_by_role('button', name='Automations', exact=True).click()
    expect(page.get_by_role('link', name='Open TechAdmin')).to_have_attribute('href', 'https://techadmin.coforge.com/')
    expect(page.get_by_role('heading', name='Source synchronization history')).to_be_visible()
    expect(page.locator('tbody tr')).to_have_count(2)
    page.close()


@pytest.fixture
async def revamp_groups_url(revamp_portal_url, session):
    from app.models.solarwinds_group import SolarWindsGroup, SolarWindsGroupMember
    from tests.factories import make_run
    session.add(SolarWindsGroup(group_id=10, name='BOCBA(Bolivia,Cochabamba-Encora)', status_code=14, status='Critical'))
    devices = [make_ci('SOLARWINDS', f'Device {i}', 'Up', 'High', attributes={'node_category': 'Server'}) for i in [1, 2]]
    session.add_all(devices)
    await session.flush()
    session.add_all([SolarWindsGroupMember(group_id=10, member_entity_type='Orion.Nodes', member_id=i, ci_id=device.id) for i, device in enumerate(devices, 1)])
    session.add(make_run('SOLARWINDS', groups_extracted=1, memberships_extracted=2))
    await session.commit()
    return revamp_portal_url


def test_group_drilldown_retries_and_preserves_exact_source_scope(revamp_groups_url, browser_context):
    page = browser_context.new_page()
    page.route('**/api/v1/solarwinds/groups/10/devices?*', lambda route: route.fulfill(status=503, json={'error': 'Unavailable'}))
    page.goto(revamp_groups_url)
    page.get_by_role('button', name='BOCBA(Bolivia,Cochabamba-Encora)', exact=True).click()
    expect(page.get_by_role('alert')).to_contain_text('Data unavailable (HTTP 503)')
    page.unroute('**/api/v1/solarwinds/groups/10/devices?*')
    page.get_by_role('button', name='Retry', exact=True).click()
    expect(page.locator('tbody tr')).to_have_count(2)
    expect(page.locator('.inventory-panel')).to_contain_text('BOCBA(Bolivia,Cochabamba-Encora)')
    expect(page.locator('.table-footer')).to_contain_text('of 2 records')
    page.get_by_role('searchbox', name='Search SolarWinds node inventory').fill('Device 2')
    expect(page.locator('tbody tr')).to_have_count(1)
    expect(page.locator('tbody')).to_contain_text('Device 2')
    page.close()


def test_site_score_status_and_monitored_percentage_remain_distinct(revamp_groups_url, browser_context):
    page = browser_context.new_page()

    def group_with_unmanaged_node(route):
        response = route.fetch()
        payload = response.json()
        group = payload['data']['items'][0]
        group['total_devices'] = 3
        group['status_breakdown'] = {'Up': 2, 'Unmanaged': 1}
        group['components']['node_status'].update(
            numerator=2, denominator=2, value=100, usable=True)
        route.fulfill(response=response, json=payload)

    page.route('**/api/v1/solarwinds/groups/overview', group_with_unmanaged_node)
    page.goto(revamp_groups_url)
    expect(page.locator('.score-card .status')).to_have_text('Healthy')
    expect(page.locator('.location-panel')).to_contain_text('100% of 2 monitored nodes')
    assert page.locator('.health-bar').evaluate('element => element.style.width') == '100%'
    expect(page.locator('.overview-panel tbody tr').first).to_contain_text('100%')
    expect(page.locator('.overview-panel tbody tr').first).to_contain_text('Critical')
    page.close()


def test_summary_failures_are_unavailable_and_global_search_reads_assets(revamp_portal_url, browser_context):
    page = browser_context.new_page()
    page.route('**/api/v1/intune/summary', lambda route: route.fulfill(status=503, json={'error': 'Unavailable'}))
    page.goto(revamp_portal_url)
    expect(page.locator('.data-notice')).to_contain_text('intune')
    expect(page.locator('.kpi-card').first).to_contain_text('—')
    expect(page.locator('.freshness')).to_contain_text('UNAVAILABLE')
    page.get_by_role('searchbox', name='Search configuration items, devices, or sites').fill('HEALTHY-SERVER')
    page.get_by_role('searchbox', name='Search configuration items, devices, or sites').press('Enter')
    expect(page.get_by_role('heading', name='Assets intelligence')).to_be_visible()
    expect(page.locator('tbody tr')).to_have_count(1)
    expect(page.locator('tbody')).to_contain_text('HEALTHY-SERVER')
    page.close()


def test_completed_source_updates_appear_without_manual_reload(revamp_portal_url, browser_context):
    page = browser_context.new_page()
    page.clock.install()
    page.goto(revamp_portal_url)
    expect(page.locator('.kpi-card').first).to_contain_text('3')
    page.route('**/api/v1/intune/summary', lambda route: route.fulfill(json={
        'metrics': {'total_managed_devices': 120, 'compliant_devices': 100, 'noncompliant_devices': 20},
        'decision_metrics': {'confirmed_compliance': {'value': 83.33}},
        'status_breakdown': {'Compliant': 100, 'NonCompliant': 20},
        'os_distribution': {'Windows': 120},
    }))
    page.clock.fast_forward(60_000)
    expect(page.locator('.kpi-card').first).to_contain_text('120')
    expect(page.locator('.kpi-card').first).to_contain_text('100 compliant')
    page.close()


@pytest.mark.parametrize('width', [320, 390, 768, 1024, 1440])
def test_layout_and_navigation_at_supported_widths(revamp_portal_url, browser_context, width):
    page = browser_context.new_page()
    page.set_viewport_size({'width': width, 'height': 900})
    page.goto(revamp_portal_url)
    page.get_by_role('button', name='Digital Workspace', exact=True).click()
    expect(page.locator('tbody tr')).to_have_count(3)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2'), page.evaluate('''() =>
        JSON.stringify({vw: innerWidth, doc: document.documentElement.scrollWidth, boxes:
          [...document.querySelectorAll('main, .app-shell, .navigation, .navigation__inner, .drilldown-target, .inventory-panel, .table-wrap, .analytics-grid')]
                    .map(el => ({class: el.className, client: el.clientWidth, scroll: el.scrollWidth, overflow: getComputedStyle(el).overflowX, right: el.getBoundingClientRect().right})),
                    escaping: [...document.querySelectorAll('.inventory-panel *')]
                    .filter(el => el.getBoundingClientRect().right > innerWidth && !el.closest('.table-wrap'))
                    .map(el => ({tag: el.tagName, class: el.className, width: el.getBoundingClientRect().width, right: el.getBoundingClientRect().right, position: getComputedStyle(el).position}))})''')
    page.get_by_role('button', name='Knowledge Center', exact=True).click()
    expect(page.get_by_role('heading', name='Knowledge Center', exact=True)).to_be_visible()
    page.close()
