const { test, expect } = require('@playwright/test');

test('full retouch flow: upload -> apply -> send to retouch -> load buffer', async ({ page }) => {
  await page.goto('http://127.0.0.1:5000');
  const { ensureAppReady } = require('./_helpers');
  await ensureAppReady(page);

  // Switch to 'Binaryzacja obrazu' tab
  await page.click('button[data-tab="image-processing"]');

  // Upload a small sample PNG that exists in the repo
  const filePath = 'data/sample_benchmark/triangle_demo_p01_r0_c0.png';
  await page.setInputFiles('#processingLoadFileInput', filePath);

  // Wait for the original image to be set and actually load (naturalWidth > 0)
  await page.waitForFunction(() => {
    const img = document.getElementById('processingOriginalImage');
    return img && img.src && img.naturalWidth > 0;
  }, { timeout: 20000 });

  // Apply preprocessing (binarization)
  await page.click('#processingApplyBtn');

  // Result should be generated and actually render
  await page.waitForFunction(() => {
    const img = document.getElementById('processingResultImage');
    return img && img.src && img.naturalWidth > 0;
  }, { timeout: 20000 });

  // Send processed result to retouch buffer
  // Wait until send button is enabled (processing finished) and then trigger it
  await page.waitForFunction(() => {
    const btn = document.getElementById('processingSendToRetouchBtn');
    return btn && !btn.disabled;
  }, { timeout: 20000 });
  await page.click('#processingSendToRetouchBtn');

  // Wait for the 'processingStatus' element and ensure it eventually shows success
  await page.waitForSelector('#processingStatus', { timeout: 20000 });
  await page.waitForFunction(() => {
    const el = document.getElementById('processingStatus');
    return el && /Wynik przekazano do retuszu|Przekazywanie materiału do retuszu/i.test(el.textContent || '');
  }, { timeout: 20000 });
  // Switch to Manual Retouch tab and then load from retouch buffer
  await page.click('button[data-tab="manual-retouch"]');
  await page.click('#retouchLoadBufferBtn');
  // Wait for the image to actually load (naturalWidth > 0) instead of relying only on visibility
  await page.waitForFunction(() => {
    const el = document.getElementById('retouchSourceImage');
    return el && el.src && el.naturalWidth > 0;
  }, { timeout: 20000 });
  // Also ensure the image actually has pixel content
  await page.waitForFunction((sel) => {
    const img = document.querySelector(sel);
    if (!img || !img.complete) return false;
    try {
      const canvas = document.createElement('canvas');
      canvas.width = img.naturalWidth; canvas.height = img.naturalHeight;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0);
      const data = ctx.getImageData(0,0, Math.max(1, canvas.width), Math.max(1, canvas.height)).data;
      for (let i = 3; i < data.length; i += 4) {
        if (data[i] > 10) return true;
      }
      return false;
    } catch (err) {
      return false;
    }
  }, '#retouchSourceImage', { timeout: 20000 });
  const src = await page.locator('#retouchSourceImage').getAttribute('src');
  expect(src).toBeTruthy();
});
