"""Standalone page regressions: all assets/API responses intercepted, no server/DB.

Also runnable with python -m unittest tests.browser.test_legacy_cmdb_truthfulness.
The optional browser suite still needs --run-browser when invoked through pytest.
"""
import copy
import json
import shutil
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[2]
SUMMARY = dict(data_available=True, total_cis=10, total_endpoints=6, total_servers=2,
               total_network_devices=1, total_unclassified=1, high_health_count=7,
               medium_health_count=2, low_health_count=1)
FRESHNESS = dict(overall_status='STALE', sources={source: dict(status='STALE',
    last_synchronized_at='2026-01-01T10:00:00+00:00', age_seconds=3600)
    for source in ['INTUNE', 'SOLARWINDS']})
ATTEMPTS = {source: dict(status='FAILED', last_completed='2026-01-01T10:30:00+00:00')
            for source in ['intune', 'solarwinds']}


class LegacyCmdbTruthfulness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise unittest.SkipTest('Playwright is not installed') from exc
        cls.playwright = sync_playwright().start()
        bundled = cls.playwright.chromium.executable_path
        executable = bundled if Path(bundled).exists() else shutil.which('chromium')
        try:
            cls.browser = cls.playwright.chromium.launch(headless=True, executable_path=executable)
        except Exception as exc:
            cls.playwright.stop()
            raise unittest.SkipTest(f'Chromium unavailable in this environment: {str(exc).splitlines()[0]}') from exc

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.summary = copy.deepcopy(SUMMARY)
        self.freshness = copy.deepcopy(FRESHNESS)
        self.attempts = copy.deepcopy(ATTEMPTS)
        self.failures = set()
        self.requests = []
        self.deferred = []
        self.defer = False
        self.context = self.browser.new_context(accept_downloads=True)
        self.addCleanup(self.context.close)
        self.context.route('**/*', self.route)
        self.page = self.context.new_page()

    def tearDown(self):
        self.assertTrue(all(request.method == 'GET' for request in self.requests))
        self.assertFalse(any('/data/' in urlsplit(r.url).path or '/sync/trigger' in r.url for r in self.requests))

    def route(self, route):
        request = route.request
        self.requests.append(request)
        url = urlsplit(request.url)
        if request.method != 'GET':
            route.abort()
            return
        responses = {'/api/v1/cmdb/summary': self.summary,
                     '/api/v1/system/freshness': self.freshness,
                     '/api/v1/sync/status': self.attempts}
        if url.path in responses:
            if self.defer:
                self.deferred.append((route, responses[url.path]))
            else:
                route.fulfill(status=503 if url.path in self.failures else 200,
                              content_type='application/json', body=json.dumps(responses[url.path]))
        elif url.path == '/api/v1/cmdb/cis':
            item = dict(id='isolated-test-ci', name='TEST ONLY ASSET', source_system='SOLARWINDS',
                        ci_type='Server', health_tier='High', status='Up', serial_number='TEST-000',
                        updated_at='2026-01-01T10:00:00+00:00')
            route.fulfill(json=dict(items=[item], total=1, total_pages=1))
        elif url.hostname == 'itom.test' and (url.path == '/cmdb_explorer.html' or url.path in
                ['/js/constants.js', '/js/services.js', '/js/utils.js']):
            path = ROOT / 'frontend' / url.path.lstrip('/')
            route.fulfill(body=path.read_bytes(), content_type='text/html' if path.suffix == '.html' else 'application/javascript')
        else:
            # Fonts/images and any unrecognized endpoint never leave the mock boundary.
            route.fulfill(status=404, body='Not provided by isolated fixture')

    def load(self):
        self.page.goto('http://itom.test/cmdb_explorer.html', wait_until='domcontentloaded')
        if not self.defer:
            self.page.wait_for_function("document.getElementById('cmdbSummaryStatus').dataset.state !== 'loading'")
            self.page.wait_for_function("!document.getElementById('cmdbIntuneSuccess').textContent.startsWith('Loading')")
            self.page.wait_for_function("!document.getElementById('cmdbIntuneAttempt').textContent.startsWith('Loading')")

    def text(self, id):
        return self.page.locator('#' + id).inner_text()

    def test_initial_loading(self):
        self.defer = True
        self.load()
        self.assertEqual(self.text('kpiTotalCis'), 'Loading…')
        self.assertIn('Loading', self.text('cmdbFreshnessText'))
        self.assertEqual(self.page.locator('#cmdbIntuneBar').evaluate('(el)=>el.style.width'), '0%')

    def test_positive_counts_health_and_provenance(self):
        self.load()
        self.assertEqual(self.text('kpiTotalCis'), '10')
        self.assertEqual(self.text('kpiEndpointsCount'), '6')
        self.assertEqual(self.text('kpiServersCount'), '4')
        self.assertEqual(self.text('kpiPassedControls'), '7')
        self.assertEqual(self.text('kpiAlertCount'), '3')
        for id, value in [('cmdbIntuneBar','60%'),('cmdbIntuneChartBar','60%'),
                          ('cmdbSolarwindsBar','40%'),('cmdbSolarwindsChartBar','40%'),('cmdbHealthBar','70%')]:
            self.assertEqual(self.page.locator('#' + id).evaluate('(el)=>el.style.width'), value)

    def test_valid_zero_is_not_replaced(self):
        self.summary = {key: 0 for key in SUMMARY}
        self.summary['data_available'] = True
        self.load()
        self.assertEqual(self.text('kpiTotalCis'), '0')
        self.assertEqual(self.text('kpiPassedControls'), '0')
        self.assertEqual(self.text('cmdbHealthShare'), 'No population')

    def test_missing_invalid_inconsistent_and_unavailable(self):
        for changes, state in [({'total_endpoints':None},'missing'),({'total_endpoints':-1},'invalid'),
                ({'total_endpoints':'6'},'invalid'),({'total_endpoints':1.5},'invalid'),
                ({'total_endpoints':5},'inconsistent'),({'data_available':False},'unavailable')]:
            with self.subTest(changes=changes):
                self.summary = dict(SUMMARY, **changes)
                self.load()
                self.assertEqual(self.page.locator('#cmdbSummaryStatus').get_attribute('data-state'), state)
                self.assertEqual(self.text('kpiTotalCis'), 'Unavailable')

    def test_missing_health_preserves_source_counts(self):
        self.summary.pop('high_health_count')
        self.load()
        self.assertEqual(self.text('kpiTotalCis'), '10')
        self.assertEqual(self.text('kpiPassedControls'), 'Unavailable')

    def test_independent_request_failures(self):
        for path in ['/api/v1/cmdb/summary','/api/v1/system/freshness','/api/v1/sync/status']:
            with self.subTest(path=path):
                self.failures = {path}
                self.load()
                self.assertEqual(self.text('kpiTotalCis'), 'Unavailable' if path.endswith('/cmdb/summary') else '10')
                if path.endswith('/system/freshness'):
                    self.assertIn('unavailable', self.text('cmdbFreshnessText'))
                else:
                    self.assertIn('STALE', self.text('cmdbFreshnessText'))
                self.assertIn('unavailable' if path.endswith('/sync/status') else 'FAILED', self.text('cmdbIntuneAttempt'))

    def test_stale_success_and_later_failed_attempt_are_separate(self):
        self.load()
        self.assertIn('2026-01-01T10:00:00+00:00', self.text('cmdbIntuneSuccess'))
        self.assertIn('STALE', self.text('cmdbIntuneSuccess'))
        self.assertIn('2026-01-01T10:30:00+00:00', self.text('cmdbIntuneAttempt'))
        self.assertIn('FAILED', self.text('cmdbIntuneAttempt'))
        self.assertIn('do not date these counts', self.page.locator('main').inner_text())

    def test_navigation_inventory_and_existing_export_are_preserved(self):
        self.load()
        self.page.locator('#cmdbTableBody').get_by_text('TEST ONLY ASSET').wait_for()
        self.assertGreater(self.page.locator('a[href="infrastructure_analytics.html"]').count(), 0)
        self.assertGreater(self.page.locator('a[href="index.html"]').count(), 0)
        with self.page.expect_download() as captured:
            self.page.get_by_role('button', name='Export CMDB CSV').click()
        download = captured.value
        self.assertIn('TEST ONLY ASSET', Path(download.path()).read_text(encoding='utf-8-sig'))
        queries = [parse_qs(urlsplit(r.url).query) for r in self.requests if urlsplit(r.url).path == '/api/v1/cmdb/cis']
        self.assertTrue(any(q.get('page_size') == ['100'] for q in queries))


if __name__ == '__main__':
    unittest.main()
