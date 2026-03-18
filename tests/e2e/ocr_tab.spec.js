const { test, expect } = require('@playwright/test');
const path = require('path');

// smoke interaction with OCR tab

test('OCR tab can trigger OCR and display results', async ({ page }) => {
  await page.goto('http://127.0.0.1:5000');
  // open OCR tab
  await page.click('button[data-tab="ocr"]');
  await expect(page.locator('#ocrRunBtn')).toBeVisible();

  // stub backend call
  await page.route('**/ocr/textract', async (route) => {
    const fake = {
      request_id: 'playwright-id',
      tokens: [],
      pairs: [{ component: 'R1', value: '10K' }],
    };
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fake) });
  });

  // attach dummy file to upload input (shared with pdf workspace)
  const filePath = path.resolve(__dirname, '../fixtures/dummy.png');
  await page.setInputFiles('#fileInput', filePath);

  // run OCR and wait for results
  await page.click('#ocrRunBtn');
  // table row should appear with component value
  await expect(page.locator('#ocrTable tbody tr')).toHaveCount(1);
  await expect(page.locator('#ocrTable tbody tr td')).toContainText('R1');
  await expect(page.locator('#ocrTable tbody tr td')).toContainText('10K');

  // verify JSON view still reflects data
  const text = await page.locator('#ocrResultsJson').textContent();
  expect(text).toContain('"value": "10K"');

  // simulate preview image and clicking it to add manual row
  const img = page.locator('#ocrImage');
  // directly set src via JS since file input isn't an image in this test
  await page.evaluate(() => {
    const img = document.getElementById('ocrImage');
    img.src = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIW2N89+/fPwAHgwJ/lPpY6AAAAABJRU5ErkJggg==';
    img.style.display = 'block';
    img.width = 10; img.height = 10;
  });
  // click near top-left and expect overlay canvas to draw
  await img.click({ position: { x: 2, y: 3 } });
  await expect(page.locator('#ocrTable tbody tr')).toHaveCount(2);
  const newRow = page.locator('#ocrTable tbody tr').nth(1);
  await expect(newRow).toHaveAttribute('data-click-x', /2\.0?/);
  await expect(newRow).toHaveAttribute('data-click-y', /3\.0?/);
  // canvas should be visible and contain some nontransparent pixel
  await expect(page.locator('#ocrOverlay')).toBeVisible();
  const hasContent = await page.evaluate(() => {
    const c = document.getElementById('ocrOverlay');
    if (!c) return false;
    const ctx = c.getContext('2d');
    const data = ctx.getImageData(0, 0, c.width, c.height).data;
    // check if any pixel has nonzero red channel
    for (let i = 0; i < data.length; i += 4) {
      if (data[i] !== 0) return true;
    }
    return false;
  });
  expect(hasContent).toBe(true);

  // now stub corrections endpoint and test save
  await page.route('**/ocr/textract/corrections', async (route) => {
    const fakeResp = { status: 'ok', path: '/fake/path.json' };
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fakeResp) });
  });

  // modify value and save
  await page.fill('#ocrTable tbody tr .val-input', '22K');
  // row should now be marked manual
  await expect(page.locator('#ocrTable tbody tr')).toHaveClass(/manual/);
  await page.click('#ocrSaveCorrectionsBtn');
  await expect(page.locator('#ocrResultsJson')).toContainText('/fake/path.json');
});
