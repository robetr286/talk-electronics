const { test, expect } = require('@playwright/test');

async function dismissWarning(page) {
  const overlayBtn = page.locator('#acceptWarning');
  if (await overlayBtn.count()) {
    await overlayBtn.click();
  }
  await expect(page.locator('#appContent')).toBeVisible();
}

async function clearIgnoreStorage(page) {
  await page.evaluate(() => {
    localStorage.removeItem('app:ignore_zones:v1');
    localStorage.removeItem('app:ignore_zones:history:v1');
  });
}

async function waitForImageProcessing(page) {
  await page.waitForFunction(() => {
    const img = document.getElementById('processingOriginalImage');
    return img && img.src && img.naturalWidth > 0;
  }, { timeout: 20000 });
}

async function getIgnoreObjectCount(page) {
  return page.evaluate(() => {
    try {
      const pre = document.getElementById('ignoreExport');
      const parsed = JSON.parse(pre.textContent || '{}');
      return Array.isArray(parsed.objects) ? parsed.objects.length : 0;
    } catch (err) {
      return -1;
    }
  });
}

test('ignore zones: draw, save, undo and expose QA history', async ({ page }) => {
  await page.goto('http://127.0.0.1:5000');
  const { ensureAppReady } = require('./_helpers');
  await ensureAppReady(page);
  await clearIgnoreStorage(page);

  await page.click('button[data-tab="image-processing"]');
  await page.setInputFiles('#processingLoadFileInput', 'data/sample_benchmark/triangle_demo_p01_r0_c0.png');
  await waitForImageProcessing(page);

  await page.click('button[data-tab="ignore-zones"]');
  const status = page.locator('#ignoreStatus');
  await expect(status).toContainText('Brak');

  await page.click('#ignoreLoadFromCropBtn');
  await expect(status).toContainText('Załadowano', { timeout: 10000 });

  const canvas = page.locator('#ignoreCanvas');
  await expect(canvas).toBeVisible();
  // Ensure the canvas has pixel content (avoid empty placeholders)
  await page.waitForFunction((sel) => {
    const canvas = document.querySelector(sel);
    if (!canvas) return false;
    try {
      const ctx = canvas.getContext('2d');
      const w = Math.max(1, canvas.width); const h = Math.max(1, canvas.height);
      const data = ctx.getImageData(0,0,w, h).data;
      for (let i = 3; i < data.length; i += 4) if (data[i] > 10) return true;
      return false;
    } catch (err) { return false; }
  }, '#ignoreCanvas', { timeout: 15000 });

  const box = await canvas.boundingBox();
  expect(box).not.toBeNull();

  const start = { x: box.x + 40, y: box.y + 40 };
  const end = { x: box.x + 200, y: box.y + 150 };
  await page.mouse.move(start.x, start.y);
  await page.mouse.down();
  await page.mouse.move(end.x, end.y);
  await page.mouse.up();

  await expect.poll(async () => getIgnoreObjectCount(page)).toBe(1);
  await page.click('#ignoreSaveBtn');
  await expect(status).toContainText('Zapisano');

  const historyItems = page.locator('#ignoreHistoryList .processing-history-item');
  await expect(historyItems).toHaveCount(1);

  await page.click('#ignoreModePoly');
  const points = [
    { x: box.x + 230, y: box.y + 60 },
    { x: box.x + 280, y: box.y + 160 },
    { x: box.x + 200, y: box.y + 210 },
  ];
  for (const pt of points) {
    await page.mouse.click(pt.x, pt.y);
  }
  await page.mouse.dblclick(points[0].x, points[0].y);
  await expect.poll(async () => getIgnoreObjectCount(page)).toBe(2);

  await page.click('#ignoreUndoBtn');
  await expect.poll(async () => getIgnoreObjectCount(page)).toBe(1);
  await expect(status).toContainText('Cofnięto');

  await historyItems.first().locator('button.load-entry').click();
  await expect.poll(async () => getIgnoreObjectCount(page)).toBe(1);
});
