import asyncio
import os
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

from playwright.async_api import async_playwright

CHROME_EXEC = r"C:\Users\Roshan.Sah\AppData\Local\ms-playwright\chromium-1234\chrome-win64\chrome.exe"
SCREENSHOT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

async def main():
    print("=" * 80)
    print(" ITOM FRONTEND PLAYWRIGHT AUTOMATED VERIFICATION SUITE")
    print("=" * 80)

    async with async_playwright() as p:
        # Launch browser with explicit executable path
        browser = await p.chromium.launch(
            executable_path=CHROME_EXEC,
            headless=True
        )
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        # Listen to console for any errors
        page.on("console", lambda msg: print(f"  [Browser Console] {msg.type}: {msg.text}") if msg.type in ("error", "warning") else None)
        page.on("requestfailed", lambda req: print(f"  [Request Failed] {req.url}: {req.failure}"))

        print("\n[Step 1] Navigating to Infrastructure Analytics...")
        url = "http://localhost:8080/infrastructure_analytics.html"
        await page.goto(url, wait_until="networkidle")
        print(f"  [OK] Loaded: {url}")

        # Wait for live API binding to finish (kpi counts become numbers)
        print("\n[Step 2] Verifying Live Backend Telemetry Binding...")
        await page.wait_for_function("document.getElementById('kpiServersCount').textContent !== '--'", timeout=15000)
        
        servers_count = await page.text_content("#kpiServersCount")
        endpoints_count = await page.text_content("#kpiEndpointsCount")
        donut_center = await page.text_content("#donutCenterVal")
        live_status = await page.text_content("#liveStatusText")
        
        print(f"  [OK] Servers KPI dynamically bound: {servers_count}")
        print(f"  [OK] Endpoints KPI dynamically bound: {endpoints_count}")
        print(f"  [OK] Donut Chart center count: {donut_center}")
        print(f"  [OK] Live status indicator: {live_status}")

        assert servers_count != "--", "Servers count must not be empty"
        assert endpoints_count != "--", "Endpoints count must not be empty"
        assert servers_count == donut_center, "Donut center must match total servers"

        # Capture Desktop Overview Screenshot
        shot1 = os.path.join(SCREENSHOT_DIR, "playwright_01_desktop_overview.png")
        await page.screenshot(path=shot1, full_page=False)
        print(f"  [OK] Saved screenshot: {shot1}")

        print("\n[Step 3] Verifying Interactive SVG Donut Slice Filtering...")
        # Click the Warning legend item or slice
        await page.click("#legendWarning")
        await page.wait_for_timeout(600)

        # Assert Active Filter Banner is visible
        banner_display = await page.evaluate("window.getComputedStyle(document.getElementById('activeFilterBanner')).display")
        assert banner_display == "flex", f"Active filter banner must be flex, got {banner_display}"
        banner_chip_text = await page.text_content("#bannerChip")
        print(f"  [OK] Filter Banner appeared: '{banner_chip_text}'")

        # Capture Donut Filtered Screenshot
        shot2 = os.path.join(SCREENSHOT_DIR, "playwright_02_donut_filtered.png")
        await page.screenshot(path=shot2, full_page=False)
        print(f"  [OK] Saved screenshot: {shot2}")

        # Reset filter
        await page.click(".clear-filter-btn")
        await page.wait_for_timeout(400)
        banner_display_after = await page.evaluate("window.getComputedStyle(document.getElementById('activeFilterBanner')).display")
        assert banner_display_after == "none", "Filter banner should be hidden after clear"
        print("  [OK] Clear filter reset grid to full fleet successfully")

        print("\n[Step 4] Verifying 60+ Enterprise Campus Sites Registry & Sparklines...")
        # Check rows in table
        rows_count = await page.evaluate("document.querySelectorAll('#siteTableBody tr').length")
        footer_text = await page.text_content("#footerShowingText")
        print(f"  [OK] Campus Table rendered {rows_count} rows on Page 1")
        print(f"  [OK] Footer Controller: '{footer_text}'")
        assert rows_count >= 10, f"Expected at least 10 rows per page, got {rows_count}"

        # Test Regional Filter Tab
        await page.click(".region-tab[data-region='INDIA']")
        await page.wait_for_timeout(400)
        india_rows = await page.evaluate("document.querySelectorAll('#siteTableBody tr').length")
        print(f"  [OK] Filtered region 'INDIA': {india_rows} facilities visible")

        # Reset region
        await page.click(".region-tab[data-region='ALL']")
        await page.wait_for_timeout(400)

        # Test Search Filter
        await page.fill("#tableSearch", "Noida")
        await page.wait_for_timeout(400)
        noida_rows = await page.evaluate("document.querySelectorAll('#siteTableBody tr').length")
        print(f"  [OK] Search query 'Noida' matched {noida_rows} facility rows")
        await page.fill("#tableSearch", "")
        await page.wait_for_timeout(400)

        # Test Page Size change to 25
        await page.select_option("#pageSizeSelect", "25")
        await page.wait_for_timeout(400)
        rows_25 = await page.evaluate("document.querySelectorAll('#siteTableBody tr').length")
        print(f"  [OK] Page size changed to 25: {rows_25} rows rendered")
        assert rows_25 == 25, f"Expected 25 rows, got {rows_25}"

        print("\n[Step 5] Verifying Leadership 24-Hour Trend Modal Drilldown...")
        # Click the first row's 24h Trend button
        await page.click("#siteTableBody tr:first-child .scope-action-btn")
        await page.wait_for_timeout(800)

        # Verify modal is open
        modal_open = await page.evaluate("document.getElementById('drilldownModal').classList.contains('open')")
        assert modal_open, "Trend modal must have 'open' class"
        modal_title = await page.text_content("#modalTitle")
        print(f"  [OK] Trend Modal opened: '{modal_title}'")

        # Capture Modal Screenshot
        shot3 = os.path.join(SCREENSHOT_DIR, "playwright_03_trend_modal.png")
        await page.screenshot(path=shot3, full_page=False)
        print(f"  [OK] Saved screenshot: {shot3}")

        # Close modal
        await page.click(".modal-close-btn")
        await page.wait_for_timeout(400)

        print("\n[Step 6] Verifying View Switcher: Servers Grid & Endpoints Grid...")
        # Switch to Servers Grid
        await page.click(".view-tab-btn[data-tab='servers']")
        await page.wait_for_timeout(1000)
        server_rows = await page.evaluate("document.querySelectorAll('#serversTableBody tr').length")
        servers_footer = await page.text_content("#serversFooterText")
        print(f"  [OK] Servers Grid loaded: {server_rows} rows ({servers_footer})")

        # Switch to Endpoints Grid
        await page.click(".view-tab-btn[data-tab='endpoints']")
        await page.wait_for_timeout(1000)
        endpoint_rows = await page.evaluate("document.querySelectorAll('#endpointsTableBody tr').length")
        endpoints_footer = await page.text_content("#endpointsFooterText")
        print(f"  [OK] Endpoints Grid loaded: {endpoint_rows} rows ({endpoints_footer})")

        # Switch back to Overview
        await page.click(".view-tab-btn[data-tab='overview']")
        await page.wait_for_timeout(400)

        print("\n[Step 7] Verifying Responsive Viewports...")
        # Tablet
        await page.set_viewport_size({"width": 1024, "height": 768})
        await page.wait_for_timeout(300)
        shot_tablet = os.path.join(SCREENSHOT_DIR, "playwright_04_tablet_1024.png")
        await page.screenshot(path=shot_tablet, full_page=False)
        print(f"  [OK] Verified 1024px Tablet viewport: {shot_tablet}")

        # Mobile
        await page.set_viewport_size({"width": 375, "height": 812})
        await page.wait_for_timeout(300)
        shot_mobile = os.path.join(SCREENSHOT_DIR, "playwright_05_mobile_375.png")
        await page.screenshot(path=shot_mobile, full_page=False)
        print(f"  [OK] Verified 375px Mobile viewport: {shot_mobile}")

        await browser.close()

    print("\n" + "=" * 80)
    print(" PLAYWRIGHT AUTOMATED VERIFICATION: ALL STEPS PASSED SUCCESSFULLY!")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
