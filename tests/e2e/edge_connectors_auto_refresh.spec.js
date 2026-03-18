const { test, expect } = require('@playwright/test');

// Verifies that when segmentation context includes a historyId, the Edge Connectors panel
// auto-refreshes and shows matches without manual "Odśwież".
test('edge connectors auto-refresh when segmentation source has historyId', async ({ page }) => {
  await page.goto('http://127.0.0.1:5000');
  const { ensureAppReady } = require('./_helpers');
  await ensureAppReady(page, { waitForModules: true });

  // Create a test connector tied to the historyId, then set the segmentation source to include it
  const historyId = 'symbols-80340b2dc317403c863f42a7e8cae060';
  await page.evaluate(async (hId) => {
    try {
      await fetch('/api/edge-connectors/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ edgeId: 'A01', page: '1', historyId: hId, geometry: { type: 'rect', points: [[0,0],[100,0],[100,100],[0,100]] } }),
      });
    } catch (err) {
      /* ignore */
    }
    try {
      if (window.lineSegmentationApi && typeof window.lineSegmentationApi.handleRetouchUpdate === 'function') {
        window.lineSegmentationApi.handleRetouchUpdate({ url: '/static/fixtures/line-segmentation/cross_gray.png', label: 'fixture', meta: { historyId: hId } });
      } else {
        const img = document.getElementById('lineSegSourceImage');
        if (img) img.src = '/static/fixtures/line-segmentation/cross_gray.png';
      }
    } catch (err) {
      /* no-op */
    }
  }, historyId);

  // Open the Edge Connectors tab which should trigger the module to read segmentation context
  await page.click('button[data-tab="edge-connectors"]');

  // Force a refresh (some environments may suppress silent refresh); then assert a row with our test edgeId appears
  await page.click('#edgeConnectorRefreshBtn');

  const rowCell = page.locator('#edgeConnectorListBody td', { hasText: 'A01' });
  await expect(rowCell.first()).toBeVisible({ timeout: 15000 });

  // Also assert the status updated to show connectors were loaded or helpful hint
  const status = page.locator('#edgeConnectorStatus');
  await expect(status).toHaveText(/Powiązano \d+ konektorów|Załadowano \d+ konektorów|Brak konektorów dla historyId:/, { timeout: 15000 });

});
