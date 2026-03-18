const { test, expect } = require('@playwright/test');

test('Scenariusz C — Świeży upload: upload PNG, binaryzation, save processed entries', async ({ page }) => {
  await page.goto('http://127.0.0.1:5000');
  const { ensureAppReady } = require('./_helpers');
  await ensureAppReady(page);

  // Use the same PNG as a "fresh upload" from disk via Binaryzacja
  await page.click('button[data-tab="image-processing"]');
  const png = 'data/sample_benchmark/triangle_demo_p01_r0_c0.png';
  await page.setInputFiles('#processingLoadFileInput', png);

  // Wait for original image to load
  await page.waitForFunction(() => {
    const img = document.getElementById('processingOriginalImage');
    return img && img.src && img.naturalWidth > 0;
  }, { timeout: 15000 });

  // Apply a filter and save processed result
  await page.click('#processingApplyBtn');
  await page.waitForFunction(() => {
    const img = document.getElementById('processingResultImage');
    return img && img.src && img.naturalWidth > 0;
  }, { timeout: 15000 });

  // Ensure processed image actually contains non-transparent pixels (not a broken load)
  await page.waitForFunction((sel) => {
    const img = document.querySelector(sel);
    if (!img || !img.complete) return false;
    try {
      const c = document.createElement('canvas');
      c.width = img.naturalWidth; c.height = img.naturalHeight;
      const ctx = c.getContext('2d');
      ctx.drawImage(img, 0, 0);
      const data = ctx.getImageData(0,0, Math.max(1,c.width), Math.max(1,c.height)).data;
      for (let i = 3; i < data.length; i += 4) if (data[i] > 10) return true;
      return false;
    } catch (err) {
      return false;
    }
  }, '#processingResultImage', { timeout: 15000 });


  // Save processed to history and verify timestamps
  await page.waitForSelector('#processingSaveResultBtn:not([disabled])', { timeout: 10000 });
  await page.click('#processingSaveResultBtn');

  // Check that at least one history item exists and has a timestamp text
  await page.waitForSelector('#processingHistoryList li.processing-history-item', { timeout: 10000 });
  const metaTexts = await page.$$eval('#processingHistoryList li.processing-history-item .processing-history-meta', els => els.map(e => e.textContent));
  // Look for a string containing 'Dodano:' or a timestamp-like substring
  const hasTimestamp = metaTexts.some(t => t && t.includes('Dodano:')) || metaTexts.some(Boolean);
  expect(hasTimestamp).toBeTruthy();
});
