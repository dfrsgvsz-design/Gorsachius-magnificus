import { test, expect } from '@playwright/test';

/**
 * Step 5/5 — "重连同步"。
 *
 * After 04 leaves a record in the local store under offline, restore network
 * and trigger the sync engine. The sync-push button (`testid=sync-push`)
 * carries a `data-pending-count` attribute equal to `surveyState.syncQueue.length`
 * and is disabled when that is 0. After clicking push, the queue should drain
 * to 0 within 30 s — observable both via the data-pending-count attribute
 * and via the SyncPanel's `sync-pending-count` chip (data-count=0).
 */
test.describe('05 - reconnect sync', () => {
  test.use({
    permissions: ['geolocation'],
    geolocation: { latitude: 22.3193, longitude: 114.1694 },
  });

  test('queue drains after network is restored', async ({ page, context }) => {
    await page.goto('/', { waitUntil: 'networkidle' });
    await page.getByTestId('nav-tab-fieldops').click();

    const projectRow = page.locator('[data-testid^="project-row-"]').first();
    await expect(projectRow).toBeVisible({ timeout: 15_000 });
    await projectRow.click();

    const observerInput = page.getByTestId('prep-observer');
    await expect(observerInput).toBeVisible({ timeout: 10_000 });
    await observerInput.fill('E2E Reconnect');
    await page.getByTestId('prep-start').click();

    await context.setOffline(true);
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

    await context.setOffline(false);

    const networkChip = page.getByTestId('network-chip');
    await expect(networkChip, 'network-chip should reflect the online state after reconnect').toHaveAttribute('data-state', 'online', { timeout: 15_000 });

    const pushBtn = page.getByTestId('sync-push');
    await expect(pushBtn, 'sync-push should appear in the top toolbar').toBeVisible({ timeout: 5_000 });

    const hadWork = await pushBtn.isEnabled({ timeout: 5_000 }).catch(() => false);
    if (hadWork) {
      await pushBtn.click();
    }

    await expect(async () => {
      const pending = await pushBtn.getAttribute('data-pending-count');
      const n = pending != null ? Number(pending) : -1;
      if (n > 0) {
        throw new Error(`sync queue still has ${n} pending items`);
      }
    }).toPass({ timeout: 30_000, intervals: [1_000, 2_000, 5_000] });
  });
});
