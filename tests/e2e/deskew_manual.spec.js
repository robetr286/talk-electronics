const { test, expect } = require('@playwright/test');

// Smoke test: upload image, go to crop tab, use manual deskew and apply angle
test('manual deskew via UI: upload -> crop -> manual deskew apply', async ({ page }) => {
  await page.goto('http://127.0.0.1:5000');
  const { ensureAppReady } = require('./_helpers');
  await ensureAppReady(page);

  // Upload sample PNG via main file input so the PDF/workspace pipeline registers it
  const filePath = 'data/sample_benchmark/triangle_demo_p01_r0_c0.png';
  await page.setInputFiles('#fileInput', filePath);
  // Click upload to trigger the PDF/workspace pipeline (same as other tests)
  await page.click('#uploadBtn');

  // Wait for PDF to be loaded into the canvas (currentPageLabel to change)
  await page.waitForFunction(() => document.getElementById('currentPageLabel')?.textContent?.trim() !== '-' , { timeout: 20000 });

  // Go to Kadrowanie tab explicitly
  await page.click('button[data-tab="crop-area"]');
  // Wait until crop canvas is visible and has been sized
  await page.waitForFunction(() => {
    const canvas = document.getElementById('cropCanvas');
    return canvas && canvas.offsetWidth > 0 && canvas.offsetHeight > 0;
  }, { timeout: 30000 });

  // Ensure the canvas has been populated with pixels (not just sized)
  await page.waitForFunction((sel) => {
    const canvas = document.querySelector(sel);
    if (!canvas) return false;
    try {
      const ctx = canvas.getContext('2d');
      const w = Math.max(1, canvas.width);
      const h = Math.max(1, canvas.height);
      const data = ctx.getImageData(0, 0, w, h).data;
      for (let i = 3; i < data.length; i += 4) {
        if (data[i] > 10) return true;
      }
      return false;
    } catch (err) {
      return false;
    }
  }, '#cropCanvas', { timeout: 30000 });

  // Zapisz zawartość canvas przed obrotem
  // Wait until canvas pixels are stable and then capture initial image
  await page.waitForTimeout(200); // tiny pause to let rendering settle
  const beforeDataUrl = await page.locator('#cropCanvas').evaluate((el) => el.toDataURL('image/png'));

  // Open manual deskew controls and set a small angle
  await page.click('#deskewManualBtn');
  await page.waitForSelector('#deskewManualControls:not(.hidden)', { timeout: 30000 });
  // Set range value via JS and dispatch input event
  await page.locator('#deskewAngleSlider').evaluate((el) => {
    el.value = '2';
    el.dispatchEvent(new Event('input'));
  });

  // Get original image dimensions from export info (e.g. "1518×725px @ 300 DPI")
  const exportText = await page.locator('#exportInfoLabel').innerText();
  const m = exportText.match(/(\d+)×(\d+)px/);
  let originalWidth = null;
  let originalHeight = null;
  if (m) {
    originalWidth = Number(m[1]);
    originalHeight = Number(m[2]);
  }

  // Intercept deskew response and verify returned width is close to original (>= 90%)
  const [resp] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith('/processing/deskew') && r.request().method() === 'POST'),
    // Wyzwól żądanie po zarejestrowaniu waitera, aby nie zgubić szybkiej odpowiedzi
    page.click('#deskewApplyBtn'),
  ]);

  // Poczekaj na komunikat potwierdzający obrócenie
  await page.waitForFunction(() => {
    const el = document.getElementById('cropInstructionText');
    return el && /Obrócono/.test(el.textContent || '');
  }, { timeout: 10000 });

  const json = await resp.json();
  expect(json.success).toBeTruthy();
  if (originalWidth) {
    expect(json.width).toBeGreaterThanOrEqual(Math.floor(originalWidth * 0.9));
  }

  // Canvas po obrocie powinien się różnić od stanu sprzed kliknięcia "Zastosuj"
  const afterDataUrl = await page.locator('#cropCanvas').evaluate((el) => el.toDataURL('image/png'));
  expect(afterDataUrl).not.toBe(beforeDataUrl);

  // Verify there is no error message in crop instructions
  await page.waitForFunction(() => {
    const el = document.getElementById('cropInstructionText');
    return el && !/Błąd prostowania|Nie można wczytać obrazu/i.test(el.textContent);
  }, { timeout: 10000 });
});

// Regression: multiple rotations + manual deskew should send canvas data (local source) and update preview
test('manual deskew after double rotate uses imageData payload', async ({ page }) => {
  await page.goto('http://127.0.0.1:5000');
  const { ensureAppReady } = require('./_helpers');
  await ensureAppReady(page);

  const filePath = 'data/sample_benchmark/triangle_demo_p01_r0_c0.png';
  await page.setInputFiles('#fileInput', filePath);
  await page.click('#uploadBtn');

  await page.waitForFunction(() => document.getElementById('currentPageLabel')?.textContent?.trim() !== '-' , { timeout: 20000 });

  await page.click('button[data-tab="crop-area"]');
  await page.waitForFunction(() => {
    const canvas = document.getElementById('cropCanvas');
    return canvas && canvas.offsetWidth > 0 && canvas.offsetHeight > 0;
  }, { timeout: 30000 });

  // Ensure canvas fully rendered before capturing
  await page.waitForTimeout(150);
  const beforeRotate = await page.locator('#cropCanvas').evaluate((el) => el.toDataURL('image/png'));

  await page.click('#rotateRightBtn');
  await page.waitForFunction(() => {
    const el = document.getElementById('cropInstructionText');
    return el && /Obrócono/.test(el.textContent || '');
  }, { timeout: 5000 });
  const afterFirstRotate = await page.locator('#cropCanvas').evaluate((el) => el.toDataURL('image/png'));
  expect(afterFirstRotate).not.toBe(beforeRotate);

  await page.click('#rotateRightBtn');
  await page.waitForFunction(() => {
    const el = document.getElementById('cropInstructionText');
    return el && /Obrócono/.test(el.textContent || '');
  }, { timeout: 5000 });

  const beforeManualDeskew = await page.locator('#cropCanvas').evaluate((el) => el.toDataURL('image/png'));

  await page.click('#deskewManualBtn');
  await page.waitForSelector('#deskewManualControls:not(.hidden)', { timeout: 5000 });
  await page.locator('#deskewAngleSlider').evaluate((el) => {
    el.value = '3.5';
    el.dispatchEvent(new Event('input'));
  });

  const [req, resp] = await Promise.all([
    page.waitForRequest((request) => request.url().endsWith('/processing/deskew') && request.method() === 'POST'),
    page.waitForResponse((response) => response.url().endsWith('/processing/deskew') && response.request().method() === 'POST'),
    page.click('#deskewApplyBtn'),
  ]);

  await page.waitForFunction(() => {
    const el = document.getElementById('cropInstructionText');
    return el && /Obrócono/.test(el.textContent || '');
  }, { timeout: 10000 });

  const body = req.postDataJSON();
  expect(body).toBeTruthy();
  expect(Math.abs(Number(body.manualAngle) - 3.5)).toBeLessThanOrEqual(0.2);
  expect(body.imageData).toBeTruthy();
  expect(body.imageUrl || null).toBeFalsy();

  const json = await resp.json();
  expect(json.success).toBeTruthy();

  const afterManualDeskew = await page.locator('#cropCanvas').evaluate((el) => el.toDataURL('image/png'));
  expect(afterManualDeskew).not.toBe(beforeManualDeskew);

  await page.waitForFunction(() => {
    const el = document.getElementById('cropInstructionText');
    return el && !/Błąd prostowania|Nie można wczytać obrazu/i.test(el.textContent);
  }, { timeout: 10000 });
});
