from playwright.sync_api import sync_playwright

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=r'C:\Users\Roshan.Sah\AppData\Local\ms-playwright\chromium-1234\chrome-win64\chrome.exe',
            headless=True
        )
        page = browser.new_page(viewport={'width': 1920, 'height': 1080})
        page.goto('http://localhost:8080/infrastructure_analytics.html')
        page.wait_for_timeout(2000)
        page.screenshot(path='docs/screenshots/audit_widescreen_overview.png')
        print('[OK] Overview screenshot captured')

        # Click Servers tab
        page.click('.view-tab-btn[data-tab=servers]')
        page.wait_for_timeout(1500)
        page.screenshot(path='docs/screenshots/audit_widescreen_servers.png')
        print('[OK] Servers tab screenshot captured')

        # Click Endpoints tab
        page.click('.view-tab-btn[data-tab=endpoints]')
        page.wait_for_timeout(1500)
        page.screenshot(path='docs/screenshots/audit_widescreen_endpoints.png')
        print('[OK] Endpoints tab screenshot captured')

        browser.close()

if __name__ == '__main__':
    main()
