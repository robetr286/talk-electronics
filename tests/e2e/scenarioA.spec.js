const { test, expect } = require('@playwright/test');

test('Scenariusz A — PDF z repo: load, navigate, save page to history', async ({ page }) => {
  await page.goto('http://127.0.0.1:5000');
  const { ensureAppReady } = require('./_helpers');
  await ensureAppReady(page);

  // Upload PDF from repo
  const pdfPath = 'data/sample_benchmark/triangle_demo.pdf';
  await page.setInputFiles('#fileInput', pdfPath);
  await page.click('#uploadBtn');

  // Wait for PDF to be loaded into the canvas (currentPageLabel to change)
  await page.waitForFunction(() => document.getElementById('currentPageLabel')?.textContent?.trim() !== '-' , { timeout: 15000 });

  // Ensure the page label shows a valid page number
  const initialPage = await page.locator('#currentPageLabel').innerText();
  expect(initialPage.trim()).toMatch(/^[0-9]+$/);

  // Switch to image-processing tab and load the current page there
  await page.click('button[data-tab="image-processing"]');
  await page.click('#processingLoadPageBtn');
  await page.waitForSelector('#processingSavePageBtn:not([disabled])', { timeout: 10000 });
  await page.click('#processingSavePageBtn');

  // Verify that an entry appears in the processing history list
  await page.waitForSelector('#processingHistoryList li.processing-history-item', { timeout: 10000 });
  const items = await page.$$eval('#processingHistoryList li.processing-history-item', els => els.length);
  expect(items).toBeGreaterThan(0);
});
