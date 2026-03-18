// Playwright configuration (example). To run UI E2E tests install Playwright (Node.js) and run `npx playwright test`.
module.exports = {
  timeout: 30 * 1000,
  // Save artifacts (videos/screenshots) into a predictable folder inside the repo for easy retrieval
  outputDir: 'tests/e2e/artifacts',
  use: {
    headless: true,
    // Recording and debug artefacts: keep lightweight defaults, capture helpful debug info only on failure
    video: 'off',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    viewport: { width: 1280, height: 720 },
  },
};
