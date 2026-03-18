const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  page.on('console', msg => console.log('PAGE LOG:', msg.type(), msg.text()));
  page.on('pageerror', err => console.log('PAGE ERROR:', err.message));
  page.on('requestfailed', req => console.log('REQUEST FAILED:', req.url(), req.failure()?.errorText));
  await page.goto('http://127.0.0.1:5000', { waitUntil: 'domcontentloaded', timeout: 60000 });
  console.log('readyState:', await page.evaluate(() => document.readyState));
  const count = await page.locator('#acceptWarning').count();
  console.log('#acceptWarning count:', count);
  const visible = await page.locator('#acceptWarning').isVisible().catch(() => false);
  console.log('#acceptWarning visible:', visible);
  // get outerHTML snippet
  const outer = await page.locator('#acceptWarning').evaluate(el => el.outerHTML).catch(() => '<none>');
  console.log('outerHTML:', outer);
  // Try to click
  try {
    await page.click('#acceptWarning', { timeout: 3000 });
    console.log('click via page.click succeeded');
  } catch (err) {
    console.log('page.click failed:', err.message);
  }
  await page.waitForTimeout(500);
  console.log('appContent visible after click:', await page.locator('#appContent').isVisible().catch(() => false));
  // Try dispatchEvent click via evaluate
  await page.evaluate(() => {
    const btn = document.getElementById('acceptWarning');
    if (btn) btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
  });
  await page.waitForTimeout(500);
  console.log('appContent visible after dispatchEvent:', await page.locator('#appContent').isVisible().catch(() => false));
  console.log('appContent classlist:', await page.locator('#appContent').evaluate(el => el.className).catch(() => '<none>'));
  await browser.close();
})();
