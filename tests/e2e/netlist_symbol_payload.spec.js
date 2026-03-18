const { test, expect } = require('@playwright/test');
const { ensureAppReady } = require('./_helpers');

// Verify that runNetlist sends `symbols` when there is no server-side symbol history id
test('runNetlist sends symbols payload fallback when symbol detections exist', async ({ page }) => {
  await page.goto('http://127.0.0.1:5000');
  const { ensureAppReady } = require('./_helpers');
  await ensureAppReady(page, { waitForModules: true });
  const apiKeys = await page.evaluate(() => Object.keys(window.lineSegmentationApi || {}));
  if (!apiKeys.includes('test__setSymbolDetections') || !apiKeys.includes('test__runNetlist')) {
    throw new Error('Required test helpers not found: ' + JSON.stringify(apiKeys));
  }

  // Inject a lightweight detection and a dummy lastResult so runNetlist proceeds
  await page.evaluate(() => {
    window.lineSegmentationApi.test__setSymbolDetections([{ label: 'R', score: 0.98, bbox: [10, 10, 20, 20] }]);
    window.lineSegmentationApi.test__setLastResult([{ dummy: true }]);
  });

  let captured = null;
  await page.route('**/api/segment/netlist', async (route) => {
    try {
      captured = JSON.parse(route.request().postData() || '{}');
    } catch (e) {
      captured = { raw: route.request().postData() };
    }
    // Respond with a netlist that does NOT include metadata.symbols to trigger client fallback
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ netlist: { metadata: { node_count: 2, edge_count: 1 } }, historyEntry: null } ),
    });
  });

  // Trigger netlist generation
  await page.evaluate(() => window.lineSegmentationApi.test__runNetlist());

  // Wait a short while for client to process
  await page.waitForTimeout(300);

  expect(captured).not.toBeNull();
  // payload should include `symbols` array (we sent one detection)
  expect(Array.isArray(captured.symbols)).toBeTruthy();
  expect(captured.symbols.length).toBe(1);

  // UI should show the fallback info about using payload symbols
  const symbolStatus = page.locator('#lineSegSymbolSummaryStatus');
  await expect(symbolStatus).toHaveText(/Powiązano .*symboli \(z payloadu\)/, { timeout: 2000 });
});

// Verify that runNetlist prefers sending symbolHistoryId when available
test('runNetlist sends symbolHistoryId when symbol history exists', async ({ page }) => {
  await page.goto('http://127.0.0.1:5000');
  await ensureAppReady(page, { waitForModules: true });

  const apiKeys = await page.evaluate(() => Object.keys(window.lineSegmentationApi || {}));
  if (!apiKeys.includes('test__setSymbolSummary') || !apiKeys.includes('test__runNetlist')) {
    throw new Error('Required test helpers not found: ' + JSON.stringify(apiKeys));
  }

  const historyId = 'symbols-test-xyz';
  await page.evaluate((h) => {
    window.lineSegmentationApi.test__setSymbolSummary({ historyId: h, summary: { count: 0 }, detections: [] });
    window.lineSegmentationApi.test__setLastResult([{ dummy: true }]);
  }, historyId);

  let captured = null;
  await page.route('**/api/segment/netlist', async (route) => {
    try {
      captured = JSON.parse(route.request().postData() || '{}');
    } catch (e) {
      captured = { raw: route.request().postData() };
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ netlist: { metadata: {} } }) });
  });

  await page.evaluate(() => window.lineSegmentationApi.test__runNetlist());
  await page.waitForTimeout(300);

  expect(captured).not.toBeNull();
  expect(captured.symbolHistoryId).toBe(historyId);
  expect(captured.symbols).toBeUndefined();
});
