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

    // Triple assertion: queue drained AND status='synced' AND no new
    // conflicts surfaced. The three checks are independent guards against
    // distinct regressions discussed in
    // `docs/release_b/sync_engine_exception_audit.md`:
    //   - pending=0       → catches "queue still has work" failures
    //   - status='synced' → catches Fix B (post-push pull failure
    //                        overwriting synced status with error)
    //   - conflicts=0     → defence against backend contract drift where
    //                        the server returns success while still
    //                        emitting conflicts (would surface here as
    //                        ``data-count > 0`` on the sync-pending chip)
    const pendingChip = page.getByTestId('sync-pending-count');
    await expect(async () => {
      const pending = Number(await pushBtn.getAttribute('data-pending-count'));
      const status = await pushBtn.getAttribute('data-status');
      if (Number.isNaN(pending) || pending > 0) {
        throw new Error(`sync queue still has ${pending} pending items`);
      }
      if (status !== 'synced') {
        throw new Error(`expected sync-push data-status='synced' after reconnect, got '${status}'`);
      }
      // sync-pending-count chip lives on the SyncPanel and is only mounted
      // on the records step. Skip if not visible (records tab not entered).
      if (await pendingChip.isVisible().catch(() => false)) {
        const chipCount = Number(await pendingChip.getAttribute('data-count'));
        if (chipCount > 0) {
          throw new Error(`sync-pending-count chip still shows ${chipCount} (server may have returned conflicts)`);
        }
      }
    }).toPass({ timeout: 30_000, intervals: [1_000, 2_000, 5_000] });

    // Fourth assertion (added by C 2026-06 in response to B's contract reply
    // on handlePushSync semantics): server may return 200 BUT mark items as
    // `queue_status:'conflict'` and populate `surveyState.conflicts`. The
    // three checks above only catch the queue-side symptoms; this catches
    // the orthogonal conflicts-side symptom by reading the SyncPanel's
    // dedicated conflict-count chip on the Records step. Defense-in-depth
    // against `lastStatus='conflict'` contract drift.
    if (await page.getByTestId('step-tab-records').isEnabled({ timeout: 2_000 }).catch(() => false)) {
      await page.getByTestId('step-tab-records').click();
      const conflictChip = page.getByTestId('sync-conflict-count');
      if (await conflictChip.isVisible({ timeout: 5_000 }).catch(() => false)) {
        await expect(
          conflictChip,
          'no NEW conflicts should appear after a clean drain (per B handlePushSync contract reply)',
        ).toHaveAttribute('data-count', '0', { timeout: 5_000 });
      }
    }
  });
});
