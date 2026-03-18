const { test, expect } = require('@playwright/test');

// Verify that when a symbol historyId is present and there's a matching history entry,
// the UI exposes a visible link to the history (lineSegSymbolHistoryLink)
test('symbol history link appears when historyId present', async ({ page }) => {
  await page.goto('http://127.0.0.1:5000');
  const { ensureAppReady } = require('./_helpers');
  await ensureAppReady(page, { waitForModules: true });

  const apiKeys = await page.evaluate(() => Object.keys(window.lineSegmentationApi || {}));
  if (!apiKeys.includes('test__setSymbolIndex') || !apiKeys.includes('test__setSymbolSummary')) {
    throw new Error('Required test helpers not found: ' + JSON.stringify(apiKeys));
  }

  const historyId = 'symbols-history-link-001';
  // Put an entry into the symbol index that matches the history id and has a URL
  await page.evaluate((h) => {
    window.lineSegmentationApi.test__setSymbolIndex([{ id: h, url: '/uploads/symbol-history/' + h }]);
    window.lineSegmentationApi.test__setSymbolSummary({ historyId: h, summary: { count: 1 }, detections: [] });
  }, historyId);

  // Make sure line-segmentation tab is visible so the link is shown
  if (await page.locator('button[data-tab="line-segmentation"]').count()) {
    await page.click('button[data-tab="line-segmentation"]');
  }

  // The history link should become visible and have the expected href
  const link = page.locator('#lineSegSymbolHistoryLink');
  await expect(link).toHaveClass(/btn/); // presence check
  await expect(link).toBeVisible();
  const href = await link.getAttribute('href');
  expect(href).toContain(historyId);
});
