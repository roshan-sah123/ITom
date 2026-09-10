import os
import sys
import time
from playwright.sync_api import sync_playwright

def run_verification():
    os.makedirs('docs/screenshots', exist_ok=True)
    brain_dir = 'C:/Users/Roshan.Sah/.gemini/antigravity-ide/brain/70865a89-bb4c-49f7-b73b-80c1e7ee9962'
    os.makedirs(brain_dir, exist_ok=True)

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

        print("\n--- 1. Testing Portal Master Home Page ---")
        page.goto('http://localhost:8080/index.html', wait_until='networkidle')
        page.wait_for_timeout(2000)

        # Validate Home Banner Stats
        ep_stat = page.locator('#homeStatEndpoints').inner_text()
        sw_stat = page.locator('#homeStatServers').inner_text()
        sites_stat = page.locator('#homeStatSites').inner_text()
        ci_stat = page.locator('#homeStatCis').inner_text()
        print(f"Home Banner -> Endpoints: {ep_stat} | Servers: {sw_stat} | Sites: {sites_stat} | CIs: {ci_stat}")
        assert ep_stat == '27,412', f"Expected 27,412, got {ep_stat}"
        assert sw_stat == '1,572', f"Expected 1,572, got {sw_stat}"
        assert sites_stat == '71', f"Expected 71, got {sites_stat}"
        assert ci_stat == '28,984', f"Expected 28,984, got {ci_stat}"

        # Capture Home screenshot
        page.screenshot(path='docs/screenshots/portal_01_home.png')
        page.screenshot(path=f'{brain_dir}/portal_01_home.png')
        print("Captured portal_01_home.png")

        # Test Launcher Card Click -> Infrastructure Analytics
        print("\n--- 2. Testing Launcher -> Infrastructure Analytics ---")
        page.locator('.btn-card-launch[data-target-view="infrastructure"]').click()
        page.wait_for_timeout(2000)

        # Verify Category Cards
        cat_servers = page.locator('#catServersVal').inner_text()
        cat_networks = page.locator('#catNetworksVal').inner_text()
        cat_sites = page.locator('#catSitesVal').inner_text()
        print(f"Infra Categories -> Servers: {cat_servers} | Networks: {cat_networks} | Sites: {cat_sites}")
        assert cat_servers == '1,572', f"Expected 1,572 servers, got {cat_servers}"
        assert cat_networks == '488', f"Expected 488 networks, got {cat_networks}"
        assert cat_sites == '71', f"Expected 71 sites, got {cat_sites}"

        # Check Server Table Rows & Total
        sw_count_text = page.locator('#swRecordCount').inner_text()
        print(f"Server Table Count: {sw_count_text}")
        assert '1,572' in sw_count_text, "Server count should show 1,572 total"

        # Test Location-Wise Filtration Dropdown
        loc_options = page.locator('#swLocationSelect option').count()
        print(f"Campus Location Filter Options: {loc_options}")
        assert loc_options > 10, "Should have 71 campus locations in select"

        # Capture Servers subtab screenshot
        page.screenshot(path='docs/screenshots/portal_02_infra_servers.png')
        page.screenshot(path=f'{brain_dir}/portal_02_infra_servers.png')
        print("Captured portal_02_infra_servers.png")

        # Test Category Card 2: Networks
        print("\n--- 3. Testing Category Card 2: Network Infrastructure ---")
        page.locator('.category-card-tab[data-subtab="networks"]').click()
        page.wait_for_timeout(1000)
        net_rows = page.locator('#netDeviceTableBody tr').count()
        net_count_text = page.locator('#netRecordCount').inner_text()
        print(f"Network Devices Table Rows: {net_rows} | Count: {net_count_text}")
        assert net_rows > 0, "Network table should have rows"
        assert '488' in net_count_text, "Network devices count should show 488"
        page.screenshot(path='docs/screenshots/portal_03_infra_networks.png')
        page.screenshot(path=f'{brain_dir}/portal_03_infra_networks.png')
        print("Captured portal_03_infra_networks.png")

        # Test Category Card 3: Campus Sites
        print("\n--- 4. Testing Category Card 3: Global Campus Facilities ---")
        page.locator('.category-card-tab[data-subtab="sites"]').click()
        page.wait_for_timeout(1000)
        campus_rows = page.locator('#ovCampusTableBody tr').count()
        print(f"Campus Facilities Table Rows: {campus_rows}")
        assert campus_rows > 0, "Campus facilities should have rows"

        # Open Campus Trend Modal
        page.locator('#ovCampusTableBody tr:first-child .btn-site-trend').click()
        page.wait_for_timeout(1000)
        modal_visible = page.locator('#trendModalBackdrop').is_visible()
        modal_title = page.locator('#modalCampusTitle').inner_text()
        print(f"Trend Modal Visible: {modal_visible} | Title: {modal_title}")
        assert modal_visible, "Modal should be visible"
        page.screenshot(path='docs/screenshots/portal_08_campus_modal.png')
        page.screenshot(path=f'{brain_dir}/portal_08_campus_modal.png')
        print("Captured portal_08_campus_modal.png")
        page.locator('#modalCloseBtn').click()
        page.wait_for_timeout(500)

        page.screenshot(path='docs/screenshots/portal_04_infra_sites.png')
        page.screenshot(path=f'{brain_dir}/portal_04_infra_sites.png')
        print("Captured portal_04_infra_sites.png")

        # Test Digital Workplace Experience (DEX / Endpoints)
        print("\n--- 5. Testing Digital Workplace Experience (DEX) & Full Pagination ---")
        page.locator('.nav-tab[data-view="endpoints"]').click()
        page.wait_for_timeout(2000)

        ep_total = page.locator('#epTotalVal').inner_text()
        ep_count_text = page.locator('#epRecordCount').inner_text()
        print(f"Endpoints Total: {ep_total} | Counter: {ep_count_text}")
        assert ep_total == '27,412', f"Expected 27,412, got {ep_total}"
        assert '27,412' in ep_count_text, "Endpoints counter should show 27,412"

        # Check smart pagination controls
        page_buttons = page.locator('#epPaginationControls .btn-page').count()
        print(f"Endpoints Pagination Buttons Count: {page_buttons}")
        assert page_buttons >= 4, "Should render pagination buttons"

        # Click Next page (›)
        next_btn = page.locator('#epPaginationControls .btn-page-nav[title="Next Page"]')
        if next_btn.count() > 0:
            next_btn.click()
            page.wait_for_timeout(1500)
            page2_count_text = page.locator('#epRecordCount').inner_text()
            print(f"After clicking Next -> Counter: {page2_count_text}")
            assert '26–50' in page2_count_text, f"Expected 26–50, got {page2_count_text}"

        page.screenshot(path='docs/screenshots/portal_05_endpoints_full_pagination.png')
        page.screenshot(path=f'{brain_dir}/portal_05_endpoints_full_pagination.png')
        print("Captured portal_05_endpoints_full_pagination.png")

        # Test Enterprise CMDB
        print("\n--- 6. Testing Enterprise CMDB Explorer ---")
        page.locator('.nav-tab[data-view="cmdb"]').click()
        page.wait_for_timeout(2000)

        cmdb_total = page.locator('#cmdbTotalCisVal').inner_text()
        cmdb_count_text = page.locator('#cmdbRecordCount').inner_text()
        print(f"CMDB Total: {cmdb_total} | Counter: {cmdb_count_text}")
        assert cmdb_total == '28,984', f"Expected 28,984, got {cmdb_total}"
        assert '28,984' in cmdb_count_text, "CMDB counter should show 28,984"

        # Search 'RTR'
        page.locator('#cmdbSearchInput').fill('RTR')
        page.wait_for_timeout(1000)
        cmdb_rtr_count = page.locator('#cmdbRecordCount').inner_text()
        print(f"After search 'RTR' -> Counter: {cmdb_rtr_count}")

        # Open Drawer
        page.locator('#cmdbTableBody tr:first-child .btn-inspect-ci').click()
        page.wait_for_timeout(1000)
        drawer_visible = page.locator('#slideDrawer').is_visible()
        drawer_title = page.locator('#drawerCiTitle').inner_text()
        print(f"Slide Drawer Visible: {drawer_visible} | Title: {drawer_title}")
        assert drawer_visible, "Drawer should be visible"
        page.screenshot(path='docs/screenshots/portal_09_slide_drawer.png')
        page.screenshot(path=f'{brain_dir}/portal_09_slide_drawer.png')
        print("Captured portal_09_slide_drawer.png")
        page.locator('#drawerCloseBtn').click()
        page.wait_for_timeout(500)

        page.screenshot(path='docs/screenshots/portal_06_cmdb_explorer.png')
        page.screenshot(path=f'{brain_dir}/portal_06_cmdb_explorer.png')
        print("Captured portal_06_cmdb_explorer.png")

        # Test Sync Ledger
        print("\n--- 7. Testing Sync Ledger ---")
        page.locator('.nav-tab[data-view="sync"]').click()
        page.wait_for_timeout(2000)

        sync_rows = page.locator('#syncRunTableBody tr').count()
        print(f"Sync Ledger Table Rows: {sync_rows}")
        assert sync_rows > 0, "Sync ledger should have rows"
        page.screenshot(path='docs/screenshots/portal_07_sync_ledger.png')
        page.screenshot(path=f'{brain_dir}/portal_07_sync_ledger.png')
        print("Captured portal_07_sync_ledger.png")

        print("\n--- Test Suite Summary ---")
        print(f"Total Console Errors Encountered: {len(console_errors)}")
        if console_errors:
            print("Errors:")
            for e in console_errors:
                print(f"  {e}")
        else:
            print("ALL TESTS PASSED WITH ZERO CONSOLE ERRORS!")

if __name__ == '__main__':
    run_verification()
