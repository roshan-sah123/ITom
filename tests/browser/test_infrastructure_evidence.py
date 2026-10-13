"""Verify missing resource measurements remain missing on screen and in CSV."""
import csv
import io

import pytest

from tests.browser.test_operator_queue import browser_context, expect

pytestmark = pytest.mark.browser


def test_infrastructure_missing_measurements_and_export(portal_url, browser_context):
    page = browser_context.new_page()

    def saturated_snapshot(route):
        response = route.fetch()
        payload = response.json()
        payload['metrics']['high_health_pct'] = 99
        payload['decision_metrics'] = {'current_node_status': {
            'value': 33.33, 'numerator': 1, 'denominator': 3,
            'coverage_pct': 100, 'unknown_records': 0,
        }}
        payload['top_saturated_servers'] = [{
            'name': 'CPU-PRESSURE', 'Caption': 'CPU-PRESSURE',
            'CPULoad': 92, 'PercentMemoryUsed': None,
        }]
        route.fulfill(response=response, json=payload)

    page.route('**/api/v1/solarwinds/summary', saturated_snapshot)
    page.goto(portal_url, wait_until='domcontentloaded')
    page.locator('.nav-tab[data-view="infrastructure"]').click()
    expect(page.locator('#subview-servers')).to_be_visible()
    expect(page.locator('.triage-item').filter(has_text='CPU-PRESSURE')).to_contain_text('RAM: Unavailable')
    expect(page.locator('#subview-servers')).to_contain_text('NODES NEEDING ATTENTION')
    expect(page.locator('#swSlaVal')).to_have_text('33.3%')
    expect(page.locator('#swAvailSub')).to_contain_text('1 / 3')
    with page.expect_download() as captured:
        page.locator('#swExportCsv').click()
    with open(captured.value.path(), encoding='utf-8-sig') as exported:
        rows = list(csv.DictReader(io.StringIO(exported.read())))
    assert rows
    assert all(row['CPU Load %'] == 'Unavailable' for row in rows)
    assert all(row['Memory Used %'] == 'Unavailable' for row in rows)
    page.close()
