import { test, expect } from '@playwright/test';

/**
 * Step 1/5 — "登录"。
 *
 * The species_monitoring_platform app is anonymous-by-default (only the admin
 * surface gates behind AdminGate). So "login" in the ticket vocabulary
 * collapses to: cold-start the SPA, wait until the React app shell mounts,
 * confirm there is no `pageerror` or console error, and the sidebar nav
 * with `data-testid="nav-tab-*"` from App.jsx is reachable.
 *
 * Selectors are testid-first per the taxonomy in tests/e2e/README.md.
 */
test.describe('01 - app boot', () => {
  test('species app boots without pageerror and shows the sidebar nav', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(`console.error: ${msg.text()}`);
    });

    await page.goto('/', { waitUntil: 'networkidle' });

    await expect(
      page.getByTestId('nav-tab-fieldops'),
      'Field Ops nav button (testid=nav-tab-fieldops) should be visible after boot',
    ).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId('nav-tab-settings')).toBeVisible();
    await expect(page.getByTestId('nav-tab-dashboard')).toBeVisible();

    const appStatusDot = page.getByTestId('app-status-dot');
    await expect(appStatusDot, 'global health status dot should be rendered').toBeVisible();

    const ignorableErrorPatterns = [
      /favicon\.ico.*404/i,
      /Failed to load resource:.*?\b404\b/i,
    ];
    const fatalErrors = errors.filter((e) => !ignorableErrorPatterns.some((p) => p.test(e)));
    expect(fatalErrors, `console / page errors during boot: ${fatalErrors.join(' | ')}`).toEqual([]);
  });
});
