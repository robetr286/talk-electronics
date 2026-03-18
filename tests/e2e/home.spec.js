const { test, expect } = require('@playwright/test');

test('load app and check retouch button presence', async ({ page }) => {
  await page.goto('http://127.0.0.1:5000');
  await expect(page).toHaveTitle(/Talk electronics/);
  // Check that button exists in DOM (it may be hidden until buffer exists)
  const btn = page.locator('#retouchLoadBufferBtn');
  await page.waitForSelector('#retouchLoadBufferBtn', { state: 'attached', timeout: 10000 });
  // It's acceptable if button is hidden or disabled until buffer exists; ensure it's present in DOM
  await expect(btn).toHaveCount(1);
});
