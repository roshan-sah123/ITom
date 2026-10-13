"""Read-only acceptance check of the running portal's evidence contracts."""
import argparse
import json
from pathlib import Path
from urllib.request import ProxyHandler, build_opener


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8080')
    parser.add_argument('--browser', action='store_true')
    args = parser.parse_args()
    base = args.url.rstrip('/')
    reader = build_opener(ProxyHandler({}))
    summaries = {}
    for source in ('intune', 'solarwinds'):
        with reader.open(f'{base}/api/v1/{source}/summary', timeout=30) as response:
            summaries[source] = json.load(response)
    for source, payload in summaries.items():
        evidence = payload['decision_metrics']
        total = payload['metrics']['total_cis']
        for name, metric in evidence.items():
            if not isinstance(metric, dict) or 'denominator' not in metric:
                continue
            assert 0 <= metric['numerator'] <= metric['denominator'] <= total, name
            assert metric['known_count'] + metric['unknown_count'] == metric['denominator'], name
            assert metric['value'] is None or 0 <= metric['value'] <= 100, name
        counts = evidence['compliance_state_counts'] if source == 'intune' else evidence['resource_health_counts']
        assert sum(counts.values()) == total
        print(f'{source}: {total:,} active records; evidence populations reconcile')
    if args.browser:
        from playwright.sync_api import sync_playwright, expect
        destination = Path('output/playwright')
        destination.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page(viewport={'width':1440, 'height':1000})
            page.route('https://fonts.googleapis.com/**', lambda route: route.abort())
            page.route('https://fonts.gstatic.com/**', lambda route: route.abort())
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(f'{base}/index.html', wait_until='domcontentloaded')
            expect(page.locator('#decisionCompliance')).not_to_have_text('—', timeout=30000)
            expect(page.locator('#decisionAvailability')).not_to_have_text('—', timeout=30000)
            expect(page.locator('#overviewRisk')).to_have_count(0)
            page.screenshot(path=str(destination/'decision-overview-live-desktop.png'), full_page=True)
            page.set_viewport_size({'width':390, 'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
            page.screenshot(path=str(destination/'decision-overview-live-mobile.png'), full_page=True)
            assert not errors, errors
            browser.close()
        print('Live desktop/mobile overview verified; no browser runtime errors')


if __name__ == '__main__':
    main()
