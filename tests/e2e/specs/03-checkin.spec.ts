import { test, expect } from '@playwright/test';

/**
 * Step 3/5 — "打点"。
 *
 * Fill prep, hit Start Survey, land in Survey step, open the observation FAB,
 * surface the ObservationFormPanel, fill species. All selectors are testid.
 */
test.describe('03 - check-in / 打点', () => {
  test.use({
    permissions: ['geolocation'],
    geolocation: { latitude: 22.3193, longitude: 114.1694 },
  });

  test('user fills prep, starts survey, opens observation form', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle' });
    await page.getByTestId('nav-tab-fieldops').click();

    const projectRow = page.locator('[data-testid^="project-row-"]').first();
    await expect(projectRow).toBeVisible({ timeout: 15_000 });
    await projectRow.click();

    const observerInput = page.getByTestId('prep-observer');
    await expect(observerInput).toBeVisible({ timeout: 10_000 });
    await observerInput.fill('E2E Observer');

    const weatherInput = page.getByTestId('prep-weather');
    if (await weatherInput.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await weatherInput.fill('Sunny');
    }

    const startBtn = page.getByTestId('prep-start');
    await expect(startBtn, 'Start Survey button should be enabled once observer is filled').toBeEnabled({ timeout: 5_000 });
    await startBtn.click();

    await expect(
      page.getByTestId('survey-end'),
      'End button is the deterministic signal we entered the Survey step',
    ).toBeVisible({ timeout: 10_000 });

    await page.getByTestId('obs-fab').click();

    const speciesInput = page.getByTestId('obs-species-input');
    await expect(speciesInput, 'Species autocomplete input should appear after FAB open').toBeVisible({ timeout: 10_000 });
    await speciesInput.fill('Gorsachius magnificus');

    await expect(
      page.getByTestId('obs-submit'),
      'Save observation button should be reachable from the form',
    ).toBeVisible({ timeout: 5_000 });
  });
});
