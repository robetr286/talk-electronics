const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  page.on('console', msg => console.log('CONSOLE', msg.type(), msg.text()));
  page.on('pageerror', err => console.error('PAGEERROR', err));
  try {
    await page.goto('http://127.0.0.1:5000', { waitUntil: 'load', timeout: 30000 });
    await page.waitForTimeout(2000);
    const apiPresent = await page.evaluate(() => typeof window.lineSegmentationApi);
    console.log('lineSegmentationApi typeof ->', apiPresent);
    const keys = await page.evaluate(() => window.lineSegmentationApi ? Object.keys(window.lineSegmentationApi) : null);
    console.log('lineSegmentationApi keys ->', keys);
  } catch (e) {
    console.error('ERROR navigating:', e);
  } finally {
    await browser.close();
  }
})();
