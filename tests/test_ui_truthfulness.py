from pathlib import Path
from html.parser import HTMLParser
import json
import re
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


def test_legacy_cmdb_initial_summary_has_no_measured_defaults():
    html = (ROOT / 'frontend/cmdb_explorer.html').read_text(encoding='utf-8')
    initial = html.split('<script>')[0]
    for claim in ['28,984', '1,572', '28,056', '928', '94.6%', '5.4%', '96.8%',
                  'Reconciled 1m ago', 'Live SWIS & Graph', 'Fleet Health Compliance',
                  'Zero Redundant History', 'Relational Ingestion Verified']:
        assert claim not in initial, claim
    assert 'Cached CMDB counts have no observation timestamp' in initial
    class SummaryIds(HTMLParser):
        def __init__(self):
            super().__init__()
            self.ids = []
        def handle_starttag(self, tag, attrs):
            ids = [value for key, value in attrs if key == 'id']
            assert len(ids) <= 1, attrs
            self.ids.extend(ids)
    parser = SummaryIds()
    parser.feed(initial)
    for id in ['cmdbIntuneBar', 'cmdbSolarwindsBar', 'cmdbHealthBar',
               'cmdbIntuneChartBar', 'cmdbSolarwindsChartBar', 'cmdbSummaryStatus',
               'cmdbIntuneSuccess', 'cmdbIntuneAttempt', 'cmdbSolarwindsSuccess', 'cmdbSolarwindsAttempt']:
        assert parser.ids.count(id) == 1, id


def test_legacy_cmdb_summary_contract_with_mocked_transport():
    """Execute the actual page/services JS with a minimal DOM; no browser/network."""
    node = shutil.which('node')
    if node is None:
        raise unittest.SkipTest('Node is required for isolated JavaScript contract checks')
    summary = dict(data_available=True, total_cis=10, total_endpoints=6,
                   total_servers=2, total_network_devices=1, total_unclassified=1,
                   high_health_count=7, medium_health_count=2, low_health_count=1)
    freshness = dict(overall_status='STALE', sources={source: dict(status='STALE',
                     last_synchronized_at='2026-01-01T10:00:00+00:00', age_seconds=3600)
                     for source in ['INTUNE', 'SOLARWINDS']})
    status = {source: dict(status='FAILED', last_completed='2026-01-01T10:30:00+00:00')
              for source in ['intune', 'solarwinds']}
    cases = [dict(summary=summary, freshness=freshness, status=status)]
    cases += [dict(summary=dict(summary, **changes), freshness=freshness, status=status)
              for changes in [dict(total_endpoints=None), dict(total_endpoints=-1),
                              dict(total_endpoints=1.5), dict(total_endpoints='6'),
                              dict(total_endpoints=5), dict(data_available=False),
                              dict(high_health_count=None), dict(high_health_count=8)]]
    cases += [dict(summary=dict(data_available=True, **{key: 0 for key in summary if key != 'data_available'}),
                   freshness=freshness, status=status)]
    cases += [dict(summary=summary, freshness=freshness, status=status, fail=path)
              for path in ['/cmdb/summary', '/system/freshness', '/sync/status']]
    omitted = dict(summary)
    omitted.pop('total_unclassified')
    cases += [dict(summary=value, freshness=freshness, status=status) for value in [
        omitted, dict(summary, total_endpoints=True), None,
        dict(summary, total_cis=4, total_endpoints=0, high_health_count=3,
             medium_health_count=1, low_health_count=0)]]
    cases.append(dict(summary=dict(data_available=False, **{key: 0 for key in summary if key != 'data_available'}),
                      freshness=freshness, status=status))
    cases.append(dict(summary=summary, status=status, freshness=dict(overall_status='FRESH', sources={
        source: dict(status='FRESH', last_synchronized_at='2026-01-01T10:00:00+00:00', age_seconds=0)
        for source in ['INTUNE', 'SOLARWINDS']})))
    script = r'''
const fs = require('fs'), vm = require('vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
(async () => {
  const results = [];
  for (const spec of input.cases) {
    const elements = {}, requests = [];
    const element = id => elements[id] ||= {textContent:'', style:{}, dataset:{}, setAttribute(){}};
    const context = {console:{warn(){},error(){}}, AbortController, setTimeout, clearTimeout,
      URLSearchParams, window:{addEventListener(){}}, document:{getElementById:element},
      fetch: async (url, options={}) => {
        requests.push(url);
        if (options.method && options.method !== 'GET') throw Error('Ingestion forbidden');
        const key = url.endsWith('/cmdb/summary') ? 'summary' : url.endsWith('/system/freshness')
          ? 'freshness' : url.endsWith('/sync/status') ? 'status' : null;
        if (!key) throw Error('Unexpected request: '+url);
        return {ok:!spec.fail || !url.endsWith(spec.fail),status:503,statusText:'Unavailable',json:async()=>spec[key]};
      }};
    context.self = context;
    vm.createContext(context);
    vm.runInContext(input.constants, context);
    vm.runInContext(input.services, context);
    vm.runInContext(input.inline, context);
    vm.runInContext('loadCmdbCis = async function() {};', context);
    await vm.runInContext('initCmdb()', context);
    const invalidCounts = vm.runInContext('[NaN, Infinity, -Infinity, Number.MAX_SAFE_INTEGER+1].map(validCount)', context);
    results.push({elements,requests,invalidCounts});
  }
  process.stdout.write(JSON.stringify(results));
})().catch(error=>{console.error(error);process.exit(1)});
'''
    html = (ROOT / 'frontend/cmdb_explorer.html').read_text(encoding='utf-8')
    inline = re.findall(r'<script>([\s\S]*?)</script>', html)[-1]
    result = subprocess.run([node, '-e', script], input=json.dumps(dict(cases=cases, inline=inline,
        services=(ROOT / 'frontend/js/services.js').read_text(encoding='utf-8'),
        constants=(ROOT / 'frontend/js/constants.js').read_text(encoding='utf-8'))),
        text=True, capture_output=True, timeout=20, check=True)
    actual = json.loads(result.stdout)
    def text(index, id):
        return actual[index]['elements'][id]['textContent']
    assert text(0, 'kpiTotalCis') == '10'
    assert text(0, 'kpiEndpointsCount') == '6'
    assert text(0, 'kpiServersCount') == '4'
    assert actual[0]['elements']['cmdbIntuneBar']['style']['width'] == '60%'
    assert actual[0]['elements']['cmdbSolarwindsBar']['style']['width'] == '40%'
    assert text(0, 'kpiPassedControls') == '7'
    assert text(0, 'kpiAlertCount') == '3'
    assert '70.0%' in text(0, 'cmdbHealthShare')
    assert 'STALE' in text(0, 'cmdbFreshnessText')
    assert '2026-01-01T10:00:00+00:00' in text(0, 'cmdbIntuneSuccess')
    assert 'FAILED' in text(0, 'cmdbIntuneAttempt')
    assert '2026-01-01T10:30:00+00:00' in text(0, 'cmdbIntuneAttempt')
    for index, state in [(1,'missing'),(2,'invalid'),(3,'invalid'),(4,'invalid'),(5,'inconsistent'),(6,'unavailable')]:
        assert actual[index]['elements']['cmdbSummaryStatus']['dataset']['state'] == state
        assert text(index, 'kpiTotalCis') == 'Unavailable'
    for index in [7, 8]:
        assert text(index, 'kpiTotalCis') == '10'
        assert text(index, 'kpiPassedControls') == 'Unavailable'
    assert text(9, 'kpiTotalCis') == '0'
    assert text(9, 'cmdbHealthShare') == 'No population'
    assert actual[9]['elements']['cmdbIntuneBar']['style']['width'] == '0%'
    assert text(10, 'kpiTotalCis') == 'Unavailable'
    assert 'STALE' in text(10, 'cmdbFreshnessText')
    assert text(11, 'kpiTotalCis') == '10'
    assert 'unavailable' in text(11, 'cmdbFreshnessText').lower()
    assert 'FAILED' in text(11, 'cmdbIntuneAttempt')
    assert text(12, 'kpiTotalCis') == '10'
    assert 'STALE' in text(12, 'cmdbFreshnessText')
    assert 'unavailable' in text(12, 'cmdbIntuneAttempt').lower()
    assert actual[13]['elements']['cmdbSummaryStatus']['dataset']['state'] == 'missing'
    assert actual[14]['elements']['cmdbSummaryStatus']['dataset']['state'] == 'invalid'
    assert actual[15]['elements']['cmdbSummaryStatus']['dataset']['state'] == 'invalid'
    assert text(16, 'kpiEndpointsCount') == '0'
    assert text(16, 'cmdbEndpointShare') == '0.0% of source records'
    assert text(17, 'kpiTotalCis') == 'Unavailable'
    assert actual[17]['elements']['cmdbSummaryStatus']['dataset']['state'] == 'unavailable'
    assert '0s old at check' in text(18, 'cmdbIntuneSuccess')
    assert 'FRESH' in text(18, 'cmdbFreshnessText')
    for item in actual:
        assert item['invalidCounts'] == [False, False, False, False]
        assert len(item['requests']) == 3
        assert all('/api/v1/' in path and '/data/' not in path for path in item['requests'])


def test_served_legacy_shells_have_no_fabricated_live_metrics():
    content = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    cmdb = (ROOT / "frontend" / "cmdb_explorer.html").read_text(encoding="utf-8")
    analytics = (ROOT / "frontend" / "infrastructure_analytics.html").read_text(encoding="utf-8")
    assert "27,412" not in content + cmdb
    assert "0% Duplicates" not in content + cmdb
    assert "PostgreSQL 16" not in content + cmdb + analytics
    assert "Fresh &lt;1m" not in analytics


def test_infrastructure_analytics_entry_does_not_self_import():
    source = (ROOT / "frontend" / "js" / "infrastructure_analytics.js").read_text(encoding="utf-8")
    assert "import './infrastructure_analytics.js'" not in source
    assert "initializeInfrastructureAnalytics" in source


def test_unavailable_storage_has_no_demo_percentages():
    source = (ROOT / "frontend" / "js" / "components" / "endpoints.js").read_text(encoding="utf-8")
    assert "renderStorageDemo" not in source
    assert "renderStorageUnavailable" in source
    assert "(demo), 68" not in source
