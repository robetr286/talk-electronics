const { test, expect } = require('@playwright/test');

test('diagnostics start button toggles relevant checkboxes', async ({ page }) => {
  await page.goto('http://127.0.0.1:5000');
  // ensure app ready helper
  const { ensureAppReady } = require('./_helpers');
  await ensureAppReady(page);

  // Open Diagnostics tab
  await page.click('.tab-btn[data-tab="diagnostics"]');
  // Wait for diagnostics panel to be attached (may be hidden due to layout), then trigger start
  await page.waitForSelector('section[data-tab-panel="diagnostics"]', { state: 'attached' });

  // Click the large hero start button (visible to users) or fallback to small button
  await page.evaluate(() => {
    const big = document.getElementById('diagnosticStartBigBtn');
    if (big) {
      big.click();
      return;
    }
    const small = document.getElementById('diagnosticStartChatBtn');
    if (small) small.click();
  });

  // Assert checkboxes are checked
  await expect(page.locator('#lineSegStoreHistory')).toBeChecked();
  await expect(page.locator('#lineSegDebug')).toBeChecked();
  // Use connector ROI may be disabled; check only if enabled
  const useRoi = page.locator('#lineSegUseConnectorRoi');
  if (await useRoi.isEnabled()) {
    await expect(useRoi).toBeChecked();
  }

  // Assert status message updated (should change from default)
  await expect(page.locator('#diagnosticChatStatus')).not.toHaveText('Brak danych.');
  // Optionally it may report 'Brak segmentów wymagających uwagi.' when no flagged segments are found.
});
