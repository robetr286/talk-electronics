const { test, expect } = require('@playwright/test');

test.describe('UI regression: symbol detection layout', () => {
  test('workspace stack is single-column and export card does not span two columns', async ({ page }) => {
    await page.goto('http://127.0.0.1:5000');
    const { ensureAppReady } = require('./_helpers');
    await ensureAppReady(page);

    // Open symbol-detection tab
    await page.click('.tab-btn[data-tab="symbol-detection"]');
    await page.waitForSelector('.tab-panel[data-tab-panel="symbol-detection"]');

    const gridTemplate = await page.evaluate(() => {
      const ws = document.querySelector('.workspace-stack.symbol-detection-stack');
      return ws ? window.getComputedStyle(ws).gridTemplateColumns : '';
    });

    expect(gridTemplate).toContain('1fr');

    const exportGrid = await page.evaluate(() => {
      const el = document.querySelector('.surface-card.export-card');
      return el ? window.getComputedStyle(el).gridColumn : '';
    });

    expect(exportGrid).not.toMatch(/span\s*2/);
  });
});
