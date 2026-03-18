const { test, expect } = require('@playwright/test');
const { ensureAppReady } = require('./_helpers');

// 1) Ensure that if status gets overwritten shortly after rendering, the micro-check restores it
test('netlist status recovers after overwrite', async ({ page }) => {
  await page.goto('http://127.0.0.1:5000');
  const { ensureAppReady } = require('./_helpers');
  await ensureAppReady(page, { waitForModules: true });
  // Dump/verify API keys – helpful for debugging CI flakes
  const apiKeys = await page.evaluate(() => Object.keys(window.lineSegmentationApi || {}));
  console.debug('lineSegmentationApi keys:', apiKeys);
  if (!apiKeys.includes('test__renderNetlist')) {
    throw new Error('lineSegmentation test helper "test__renderNetlist" not found. Keys: ' + JSON.stringify(apiKeys));
  }
  // Bring the tab into view if actionable; if hidden, continue because helpers are available
  try {
    if (await page.locator('button[data-tab="line-segmentation"]').count()) {
      await page.click('button[data-tab="line-segmentation"]');
      await page.waitForSelector('#lineSegNetlistStatus', { state: 'visible', timeout: 5000 });
    }
  } catch (e) {
    // ignore — we only need API helpers to be present
    console.warn('Could not activate line-segmentation tab, continuing with API helpers');
  }

  const warnings = [];
  page.on('console', (msg) => {
    if (msg.type() === 'warning' && msg.text().includes('renderNetlist: status was overwritten')) {
      warnings.push(msg.text());
    }
  });

  // Synthetic netlist with nodes to trigger renderNetlist path
  const netlist = {
    metadata: {
      node_count: 2,
      edge_count: 1,
      netlist: ['N1 1 2'],
      nodes: [{ id: 'n1' }, { id: 'n2' }],
    },
    nodes: [{ id: 'n1' }, { id: 'n2' }],
  };

  await page.evaluate(async (nl) => {
    // Render netlist (schedules micro-check)
    if (window.lineSegmentationApi && typeof window.lineSegmentationApi.test__renderNetlist === 'function') {
      window.lineSegmentationApi.test__renderNetlist(nl);
      // Simulate a race: another piece of code overwrites status shortly after
      setTimeout(() => {
        if (window.lineSegmentationApi && typeof window.lineSegmentationApi.test__forceOverwriteStatus === 'function') {
          window.lineSegmentationApi.test__forceOverwriteStatus('Brak danych.');
        } else {
          const el = document.getElementById('lineSegNetlistStatus');
          if (el) el.textContent = 'Brak danych.';
        }
      }, 10);
    } else {
      throw new Error('lineSegmentation test helpers not available');
    }
  }, netlist);

  // Wait for status to be restored to Netlista gotowa.
  const status = page.locator('#lineSegNetlistStatus');
  await expect(status).toHaveText('Netlista gotowa.', { timeout: 5000 });

  // Allow a short period for micro-check to run; primary assertion is status restoration
  await page.waitForTimeout(50);
});

// 2) Ensure exporting SPICE shows helpful reason when there are 0 component assignments
test('spice export shows reason when no component assignments', async ({ page }) => {
  await page.goto('http://127.0.0.1:5000');
  const { ensureAppReady } = require('./_helpers');
  await ensureAppReady(page, { waitForModules: true });
  // Dump/verify API keys – helpful for debugging CI flakes
  const apiKeys = await page.evaluate(() => Object.keys(window.lineSegmentationApi || {}));
  console.debug('lineSegmentationApi keys:', apiKeys);
  if (!apiKeys.includes('test__renderNetlist')) {
    throw new Error('lineSegmentation test helper "test__renderNetlist" not found. Keys: ' + JSON.stringify(apiKeys));
  }
  // Bring the tab into view if actionable; if hidden, continue because helpers are available
  try {
    if (await page.locator('button[data-tab="line-segmentation"]').count()) {
      await page.click('button[data-tab="line-segmentation"]');
      await page.waitForSelector('#lineSegNetlistStatus', { state: 'visible', timeout: 5000 });
    }
  } catch (e) {
    // ignore — we only need API helpers to be present
    console.warn('Could not activate line-segmentation tab, continuing with API helpers');
  }

  const netlist = {
    metadata: {
      node_count: 3,
      edge_count: 2,
      netlist: ['N1 1 2', 'N2 2 3'],
      nodes: [{ id: 'n1' }, { id: 'n2' }, { id: 'n3' }],
    },
    nodes: [{ id: 'n1' }, { id: 'n2' }, { id: 'n3' }],
  };

  // Ensure there are no symbol detections and render the netlist
  await page.evaluate(async (nl) => {
    if (!window.lineSegmentationApi) throw new Error('lineSegmentationApi not found');
    if (typeof window.lineSegmentationApi.test__setSymbolDetections === 'function') {
      window.lineSegmentationApi.test__setSymbolDetections([]);
    }
    if (typeof window.lineSegmentationApi.test__renderNetlist === 'function') {
      window.lineSegmentationApi.test__renderNetlist(nl);
    }
  }, netlist);

  // Click export to SPICE
  await page.click('#lineSegSpiceExportBtn');

  const spiceStatus = page.locator('#lineSegSpiceStatus');
  await expect(spiceStatus).toHaveText(/Powód: .*Brak wykrytych symboli|Brak wykrytych symboli/, { timeout: 3000 });
});
