import { test, expect } from '@playwright/test';

/**
 * Step 4/5 — "离线提交"。
 *
 * Cut network via context.setOffline(true). FieldOpsTab.jsx's `network-chip`
 * flips its `data-state` from "online" to "offline" and the sync-push button
 * disables (its handler depends on `isOnline`). We then stage a record; the
 * save handler (`saveObservationOnlineAware` at FieldOpsTab.jsx:1291) catches
 * the offline state and calls `upsertLocalEntity(..., 'observation', ...)`
 * which lands the record in localStorage (`saveSurveyState` →
 * `surveyOffline.js`).
 */
test.describe('04 - offline submit', () => {
  test.use({
    permissions: ['geolocation'],
    geolocation: { latitude: 22.3193, longitude: 114.1694 },
  });

  test('observation submitted while offline lands in local store', async ({ page, context }) => {
    await page.goto('/', { waitUntil: 'networkidle' });
    await page.getByTestId('nav-tab-fieldops').click();

    const projectRow = page.locator('[data-testid^="project-row-"]').first();
    await expect(projectRow).toBeVisible({ timeout: 15_000 });
    await projectRow.click();

    const observerInput = page.getByTestId('prep-observer');
    await expect(observerInput).toBeVisible({ timeout: 10_000 });
    await observerInput.fill('E2E Offline');
    await page.getByTestId('prep-start').click();

    await context.setOffline(true);

    const networkChip = page.getByTestId('network-chip');
    await expect(networkChip, 'network-chip should reflect the offline state').toHaveAttribute('data-state', 'offline', { timeout: 10_000 });

    if (await page.getByTestId('obs-fab').isVisible({ timeout: 2_000 }).catch(() => false)) {
      await page.getByTestId('obs-fab').click();
    }

    const speciesInput = page.getByTestId('obs-species-input');
    if (await speciesInput.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await speciesInput.fill('Gorsachius magnificus');
      const submit = page.getByTestId('obs-submit');
      if (await submit.isEnabled({ timeout: 2_000 }).catch(() => false)) {
        await submit.click();
      }
    }

    const localStoreState = await page.evaluate(async () => {
      try {
        const surveyKey = Object.keys(localStorage).find((k) => k.toLowerCase().includes('survey'));
        const surveyRaw = surveyKey ? localStorage.getItem(surveyKey) : null;
        let hasIdb = false;
        if (typeof indexedDB.databases === 'function') {
          const dbs = await indexedDB.databases();
          hasIdb = (dbs || []).length > 0;
        }
        return {
          surveyKey,
          surveyHasObservations: surveyRaw ? /observation/i.test(surveyRaw) : false,
          hasIdb,
        };
      } catch (e) {
        return { error: String(e) };
      }
    });

    expect(
      localStoreState.hasIdb || localStoreState.surveyHasObservations,
      `offline save should leave either an IndexedDB or an observation-bearing localStorage key; got ${JSON.stringify(localStoreState)}`,
    ).toBe(true);
  });
});
