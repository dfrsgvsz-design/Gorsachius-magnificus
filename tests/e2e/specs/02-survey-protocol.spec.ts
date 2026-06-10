import { test, expect } from '@playwright/test';

/**
 * Step 2/5 — "选调查协议"。
 *
 * Drill from project picker → site picker (the protocol picker proper
 * is route-level; for the gate we only need to prove the drill works).
 * FieldOpsTab auto-creates a default project named after the configured
 * study region on first launch (see FieldOpsTab.jsx:694-712), so the
 * project list is guaranteed non-empty when the platform config has loaded.
 *
 * Selectors are testid-first per tests/e2e/README.md taxonomy.
 */
test.describe('02 - survey protocol selection', () => {
  test('field ops tab loads, default project visible, drill into sites', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle' });

    await page.getByTestId('nav-tab-fieldops').click();

    await expect(page.getByTestId('step-tab-setup'), 'Setup step tab should be visible').toBeVisible({ timeout: 10_000 });

    const levelHeader = page.getByTestId('setup-level-header');
    await expect(levelHeader).toHaveAttribute('data-level', 'projects', { timeout: 10_000 });

    const projectRow = page.locator('[data-testid^="project-row-"]').first();
    await expect(projectRow, 'at least one project row should be present (auto-created default)').toBeVisible({ timeout: 15_000 });
    await projectRow.click();

    await expect(levelHeader, 'header should switch to sites level after project pick').toHaveAttribute('data-level', 'sites', { timeout: 10_000 });

    const prepObserver = page.getByTestId('prep-observer');
    if (await prepObserver.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await expect(prepObserver, 'prep observer input should be reachable on the same screen').toBeVisible();
    }
  });
});
