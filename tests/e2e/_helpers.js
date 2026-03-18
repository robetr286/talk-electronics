/**
 * Ensure the app UI is ready for tests.
 * Options:
 *  - waitForModules: wait for window.lineSegmentationApi to be present
 *  - acceptOverlay: whether to automatically click '#acceptWarning' overlay (default: true locally, false in CI)
 */
async function ensureAppReady(page, { waitForModules = false, acceptOverlay = undefined } = {}) {
  // Default: accept overlay by default (including in CI). Can be disabled by setting AUTO_ACCEPT_OVERLAY=false in the environment.
  if (acceptOverlay === undefined) {
    acceptOverlay = process.env.AUTO_ACCEPT_OVERLAY !== 'false';
  }

  // Dismiss welcome/alert overlay if present and allowed.
  // Attempt to detect and click the overlay for a brief window because it may appear slightly after page load.
  try {
    if (acceptOverlay) {
      const accept = page.locator('#acceptWarning');
      const maxWait = 10000; // ms
      const start = Date.now();
      while ((Date.now() - start) < maxWait) {
        if (await accept.count()) {
          try {
            await accept.click();
            // Wait briefly to allow any handler to run and the app to unhide content
            await page.waitForTimeout(250);
            if (await page.locator('#appContent').isVisible()) break;
            // If click didn't reveal app, continue trying until timeout
          } catch (err) {
            // If click fails (not clickable yet), wait and retry
          }
        }
        await page.waitForTimeout(150);
      }
    }
  } catch (e) {
    // no-op
  }

  // Wait for main app content to be visible
  await page.waitForSelector('#appContent', { state: 'visible', timeout: 30000 });

  // Give a small pause for scripts to attach
  await page.waitForTimeout(150);

  if (waitForModules) {
    // Wait for core module initialisation (lineSegmentationApi) to be present
    await page.waitForFunction(() => Boolean(window.lineSegmentationApi), { timeout: 30000 });
  }
}

module.exports = { ensureAppReady };
