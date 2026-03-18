const { test, expect } = require('@playwright/test');

test('diagnostics corrections modal saves and updates readiness', async ({ page }) => {
  await page.goto('http://127.0.0.1:5000');
  const { ensureAppReady } = require('./_helpers');
  await ensureAppReady(page);

  // Simulate readiness endpoint with toggleable state
  let readyState = false;
  await page.route('**/api/diagnostics/readiness', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        symbols_detected: true,
        netlist_generated: readyState,
        labels_coverage_pct: readyState ? 95 : 50,
        values_coverage_pct: readyState ? 96 : 40,
        avg_confidence: readyState ? 0.9 : 0.6,
        missing: readyState ? [] : ['netlist','component_values'],
        ready: readyState,
      }),
    });
  });

  // Intercept POST corrections and flip readiness
  let capturedPost = null;
  await page.route('**/api/diagnostics/corrections', async (route) => {
    const req = route.request();
    capturedPost = await req.postDataJSON();
    readyState = true; // simulate server recomputation
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, applied: Object.keys(capturedPost.corrections || {}) }) });
  });

  // Open Diagnostics tab
  await page.click('.tab-btn[data-tab="diagnostics"]');
  await page.waitForSelector('#diagnosticEditBtn');

  // Open modal
  await page.click('#diagnosticEditBtn');
  await page.waitForSelector('#diagnosticEditModal', { state: 'visible' });

  // Fill JSON and save
  const sample = { R1: { value: '10kΩ' }, C1: { label: 'C1', value: '100µF' } };
  await page.fill('#diagnosticEditTextarea', JSON.stringify(sample));

  // Handle alert dialog (success)
  page.once('dialog', async (dialog) => {
    expect(dialog.message()).toContain('Poprawki zapisane');
    await dialog.accept();
  });

  await page.click('#diagnosticEditSave');

  // Ensure POST was captured
  await expect.poll(() => !!capturedPost, { timeout: 2000 }).toBeTruthy();
  expect(capturedPost).toHaveProperty('corrections');
  expect(Object.keys(capturedPost.corrections)).toEqual(expect.arrayContaining(['R1', 'C1']));

  // After server reply, readiness should reflect readyState
  await expect(page.locator('#diagnostics-readiness')).toHaveText(/Gotowe/i);
  await expect(page.locator('#checkbox-symbols')).toBeChecked();
  await expect(page.locator('#checkbox-netlist')).toBeChecked();
  await expect(page.locator('#checkbox-values')).toBeChecked();
  await expect(page.locator('#diagnosticStartBtn')).toBeEnabled();
});
