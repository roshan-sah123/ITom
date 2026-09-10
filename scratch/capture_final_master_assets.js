const { chromium } = require('C:/Users/Roshan.Sah/AppData/Local/ms-playwright-go/1.57.0/package');
const path = require('path');
const fs = require('fs');

(async () => {
  try {
    const browser = await chromium.launch({
      executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
      headless: true
    });
    const page = await browser.newPage({ viewport: { width: 1440, height: 1250 } });
    
    // 1. Capture Master Overview
    await page.goto('http://127.0.0.1:8080/final_master_reference_asset.html', { waitUntil: 'networkidle' });
    await page.waitForTimeout(600);

    const destDir1 = 'c:\\Users\\Roshan.Sah\\Documents\\antigravity\\optimistic-pasteur\\frontend\\demo_previews';
    const destDir2 = 'c:\\Users\\Roshan.Sah\\Documents\\antigravity\\optimistic-pasteur\\docs\\demo_previews';

    const p1 = path.join(destDir1, 'final_master_reference_dashboard.png');
    await page.screenshot({ path: p1, fullPage: true });
    console.log('Saved 1:', p1);

    // 2. Click Donut Slice / Legend to demonstrate dynamic filtering
    await page.click('#legendWarning');
    await page.waitForTimeout(600);

    const p2 = path.join(destDir1, 'final_master_donut_filter_interaction.png');
    await page.screenshot({ path: p2, fullPage: true });
    console.log('Saved 2:', p2);

    // 3. Open Drilldown Modal (Endpoints IA-01)
    await page.click('.clear-filter-btn');
    await page.waitForTimeout(300);
    await page.click('.category-card[data-domain="endpoints"]');
    await page.waitForTimeout(500);

    const p3 = path.join(destDir1, 'final_master_drilldown_modal.png');
    await page.screenshot({ path: p3, fullPage: false });
    console.log('Saved 3:', p3);

    // Also copy to docs/demo_previews
    fs.copyFileSync(p1, path.join(destDir2, 'final_master_reference_dashboard.png'));
    fs.copyFileSync(p2, path.join(destDir2, 'final_master_donut_filter_interaction.png'));
    fs.copyFileSync(p3, path.join(destDir2, 'final_master_drilldown_modal.png'));
    console.log('Successfully synced all captures to docs/demo_previews!');

    await browser.close();
  } catch (err) {
    console.error('Error in capture:', err);
    process.exit(1);
  }
})();
