import os
import sys
import time
from playwright.sync_api import sync_playwright

def run_verification():
    os.makedirs('docs/screenshots', exist_ok=True)
    os.makedirs('C:/Users/Roshan.Sah/.gemini/antigravity-ide/brain/70865a89-bb4c-49f7-b73b-80c1e7ee9962', exist_ok=True)

    console_errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=r"C:\Users\Roshan.Sah\AppData\Local\ms-playwright\chromium-1234\chrome-win64\chrome.exe",
            headless=True
        )
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()

        def handle_console(msg):
            if msg.type == 'error':
                console_errors.append(msg.text)
                print(f"[Browser Console Error]: {msg.text}")
        page.on('console', handle_console)

        print("\n--- 1. Testing Overview & Pulse View ---")
        page.goto('http://localhost:8080/index.html', wait_until='networkidle')
        page.wait_for_timeout(2000)

        # Validate Overview KPIs
        endpoints_val = page.locator('#ovEndpointsCount').inner_text()
        servers_val = page.locator('#ovServersCount').inner_text()
        print(f"Overview Endpoints: {endpoints_val} | Servers: {servers_val}")
        assert endpoints_val != '0', "Endpoints count should not be 0"
        assert servers_val != '0', "Servers count should not be 0"

        # Validate Campus table has rows
        campus_rows = page.locator('#ovCampusTableBody tr').count()
        print(f"Campus Table Rows: {campus_rows}")
        assert campus_rows > 0, "Campus table should have rows"

        # Click regional filter 'INDIA'
        page.locator('.campus-reg-tab[data-region="INDIA"]').click()
        page.wait_for_timeout(500)
        india_rows = page.locator('#ovCampusTableBody tr').count()
        print(f"India Campus Rows: {india_rows}")

        # Open Campus Trend Modal
        first_trend_btn = page.locator('#ovCampusTableBody tr:first-child .btn-site-trend')
        if first_trend_btn.count() > 0:
            first_trend_btn.click()
            page.wait_for_timeout(1000)
            modal_visible = page.locator('#trendModalBackdrop').is_visible()
            modal_title = page.locator('#modalCampusTitle').inner_text()
            print(f"Trend Modal Visible: {modal_visible} | Title: {modal_title}")
            assert modal_visible, "Modal should be visible"
            page.locator('#modalCloseBtn').click()
            page.wait_for_timeout(500)

        page.screenshot(path='docs/screenshots/modular_01_overview.png')
        page.screenshot(path='C:/Users/Roshan.Sah/.gemini/antigravity-ide/brain/70865a89-bb4c-49f7-b73b-80c1e7ee9962/modular_01_overview.png')
        print("Captured screenshot: modular_01_overview.png")

        print("\n--- 2. Testing Hybrid Servers View ---")
        page.locator('.nav-tab[data-view="servers"]').click()
        page.wait_for_timeout(2000)

        sw_total = page.locator('#swTotalNodesVal').inner_text()
        sw_sla = page.locator('#swSlaVal').inner_text()
        print(f"Servers Total: {sw_total} | SLA: {sw_sla}")
        assert sw_total != '0', "Servers total should not be 0"

        sw_rows = page.locator('#swServerTableBody tr').count()
        print(f"Server Table Rows: {sw_rows}")
        assert sw_rows > 0, "Server table should have rows"

        # Open Drawer
        first_inspect_btn = page.locator('#swServerTableBody tr:first-child .btn-inspect-node')
        if first_inspect_btn.count() > 0:
            first_inspect_btn.click()
            page.wait_for_timeout(1000)
            drawer_visible = page.locator('#slideDrawer').is_visible()
            drawer_title = page.locator('#drawerCiTitle').inner_text()
            print(f"Slide Drawer Visible: {drawer_visible} | Title: {drawer_title}")
            assert drawer_visible, "Drawer should be visible"
            page.locator('#drawerCloseBtn').click()
            page.wait_for_timeout(500)

        page.screenshot(path='docs/screenshots/modular_02_servers.png')
        page.screenshot(path='C:/Users/Roshan.Sah/.gemini/antigravity-ide/brain/70865a89-bb4c-49f7-b73b-80c1e7ee9962/modular_02_servers.png')
        print("Captured screenshot: modular_02_servers.png")

        print("\n--- 3. Testing Digital Workplace Endpoints View ---")
        page.locator('.nav-tab[data-view="endpoints"]').click()
        page.wait_for_timeout(2000)

        ep_total = page.locator('#epTotalVal').inner_text()
        ep_comp = page.locator('#epCompRateVal').inner_text()
        print(f"Endpoints Total: {ep_total} | Compliance Rate: {ep_comp}")
        assert ep_total != '0', "Endpoints total should not be 0"

        ep_rows = page.locator('#epDeviceTableBody tr').count()
        print(f"Endpoint Table Rows: {ep_rows}")
        assert ep_rows > 0, "Endpoints table should have rows"

        page.screenshot(path='docs/screenshots/modular_03_endpoints.png')
        page.screenshot(path='C:/Users/Roshan.Sah/.gemini/antigravity-ide/brain/70865a89-bb4c-49f7-b73b-80c1e7ee9962/modular_03_endpoints.png')
        print("Captured screenshot: modular_03_endpoints.png")

        print("\n--- 4. Testing CMDB Explorer View ---")
        page.locator('.nav-tab[data-view="cmdb"]').click()
        page.wait_for_timeout(2000)

        cmdb_total = page.locator('#cmdbTotalCisVal').inner_text()
        cmdb_intune = page.locator('#cmdbIntuneProvVal').inner_text()
        print(f"CMDB Total CIs: {cmdb_total} | Intune Provenance: {cmdb_intune}")
        assert cmdb_total != '0', "CMDB total should not be 0"

        cmdb_rows = page.locator('#cmdbTableBody tr').count()
        print(f"CMDB Table Rows: {cmdb_rows}")
        assert cmdb_rows > 0, "CMDB table should have rows"

        # Search test in CMDB
        page.locator('#cmdbSearchInput').fill('RTR')
        page.wait_for_timeout(1000)
        filtered_cmdb_rows = page.locator('#cmdbTableBody tr').count()
        print(f"CMDB Search 'RTR' matching rows: {filtered_cmdb_rows}")

        page.screenshot(path='docs/screenshots/modular_04_cmdb.png')
        page.screenshot(path='C:/Users/Roshan.Sah/.gemini/antigravity-ide/brain/70865a89-bb4c-49f7-b73b-80c1e7ee9962/modular_04_cmdb.png')
        print("Captured screenshot: modular_04_cmdb.png")

        print("\n--- 5. Testing Sync Ledger View ---")
        page.locator('.nav-tab[data-view="sync"]').click()
        page.wait_for_timeout(2000)

        sync_rows = page.locator('#syncLedgerTableBody tr').count()
        print(f"Sync Ledger Rows: {sync_rows}")

        page.screenshot(path='docs/screenshots/modular_05_sync.png')
        page.screenshot(path='C:/Users/Roshan.Sah/.gemini/antigravity-ide/brain/70865a89-bb4c-49f7-b73b-80c1e7ee9962/modular_05_sync.png')
        print("Captured screenshot: modular_05_sync.png")

        browser.close()

    print("\n--- Test Suite Summary ---")
    print(f"Total Console Errors Encountered: {len(console_errors)}")
    if console_errors:
        print("Errors:\n" + "\n".join(console_errors))
    else:
        print("ALL TESTS PASSED WITH ZERO CONSOLE ERRORS!")

if __name__ == '__main__':
    run_verification()
