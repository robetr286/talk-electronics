const { test, expect } = require('@playwright/test');

test('diagnostics readiness checklist updates from API', async ({ page }) => {
  await page.goto('http://127.0.0.1:5000');
  const { ensureAppReady } = require('./_helpers');
  await ensureAppReady(page);

  // Stub initial readiness (partial/not ready)
  await page.route('**/api/diagnostics/readiness', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        symbols_detected: true,
        netlist_generated: false,
        labels_coverage_pct: 50,
        values_coverage_pct: 40,
        avg_confidence: 0.6,
        missing: ['netlist', 'component_values'],
        ready: false,
      }),
    });
  });

  // Open Diagnostics tab and wait for checklist to be filled
  await page.click('.tab-btn[data-tab="diagnostics"]');

  // Check initial state: not ready (symbols detected, others missing)
  await expect(page.locator('#diagnostics-readiness')).toHaveText(/Brak|⚠️/i);
  await expect(page.locator('#checkbox-symbols')).toBeChecked();
  await expect(page.locator('#checkbox-netlist')).not.toBeChecked();
  await expect(page.locator('#diagnosticStartBtn')).toBeDisabled();

  // Now update route to return ready state
  await page.route('**/api/diagnostics/readiness', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        symbols_detected: true,
        netlist_generated: true,
        labels_coverage_pct: 92,
        values_coverage_pct: 95,
        avg_confidence: 0.9,
        missing: [],
        ready: true,
      }),
    });
  });

  // Trigger refresh in page (calls the fetch and updates UI)
  await page.evaluate(async () => {
    if (window.diagnosticChatApi && typeof window.diagnosticChatApi.refreshReadiness === 'function') {
      await window.diagnosticChatApi.refreshReadiness();
    }
  });

  // Check updated state: ready
  await expect(page.locator('#diagnostics-readiness')).toHaveText(/Gotowe/i);
  await expect(page.locator('#checkbox-symbols')).toBeChecked();
  await expect(page.locator('#checkbox-netlist')).toBeChecked();
  await expect(page.locator('#checkbox-labels')).toBeChecked();
  await expect(page.locator('#diagnosticStartBtn')).toBeEnabled();
});
