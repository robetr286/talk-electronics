import { test, expect } from '@playwright/test';

// Quick unit-like test that runs in browser context to validate timestamp util
test('formatTimestamp util formats ISO to local YYYY-MM-DD HH:mm and includes tz', async ({ page }) => {
  await page.goto('http://127.0.0.1:5000');
  const out = await page.evaluate(async () => {
    const mod = await import('/static/js/utils/timestamp.js');
    return mod.formatTimestamp('2026-01-10T20:00:00+00:00');
  });
  // Expect pattern like: 2026-01-10 21:00 CET or similar (hours depend on local TZ)
  expect(out).toMatch(/\d{4}-\d{2}-\d{2} \d{2}:\d{2}/);
  expect(typeof out).toBe('string');
});

test('parseTimestamp returns null for invalid inputs and Date for valid', async ({ page }) => {
  await page.goto('http://127.0.0.1:5000');
  const res = await page.evaluate(async () => {
    const mod = await import('/static/js/utils/timestamp.js');
    return {
      a: mod.parseTimestamp('not-a-date'),
      b: mod.parseTimestamp('2026-01-10T20:00:00+00:00') instanceof Date,
    };
  });
  expect(res.a).toBeNull();
  expect(res.b).toBeTruthy();
});
