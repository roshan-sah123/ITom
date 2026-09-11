from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path=r'C:\Users\Roshan.Sah\AppData\Local\ms-playwright\chromium-1234\chrome-win64\chrome.exe',
        headless=True
    )
    page = browser.new_page(viewport={'width': 1920, 'height': 1080})
    page.goto('http://localhost:8080/index.html', wait_until='networkidle')
    page.wait_for_timeout(2000)

    # 1. Open Campus Trend Modal
    page.locator('#ovCampusTableBody tr:first-child .btn-site-trend').click()
    page.wait_for_timeout(1000)
    page.screenshot(path='docs/screenshots/modular_06_trend_modal.png')
    page.screenshot(path='C:/Users/Roshan.Sah/.gemini/antigravity-ide/brain/70865a89-bb4c-49f7-b73b-80c1e7ee9962/modular_06_trend_modal.png')
    print('Captured modular_06_trend_modal.png')

    # Close modal
    page.locator('#modalCloseBtn').click()
    page.wait_for_timeout(500)

    # 2. Switch to servers and open Drawer
    page.locator(".nav-tab[data-view='servers']").click()
    page.wait_for_timeout(2000)
    page.locator('#swServerTableBody tr:first-child .btn-inspect-node').click()
    page.wait_for_timeout(1000)
    page.screenshot(path='docs/screenshots/modular_07_slide_drawer.png')
    page.screenshot(path='C:/Users/Roshan.Sah/.gemini/antigravity-ide/brain/70865a89-bb4c-49f7-b73b-80c1e7ee9962/modular_07_slide_drawer.png')
    print('Captured modular_07_slide_drawer.png')
