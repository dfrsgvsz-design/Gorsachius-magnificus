import { defineConfig, devices } from '@playwright/test';

/**
 * Cross-app E2E harness. Created 2026-06-10 (ticket #C, Batch 2).
 *
 * Replaces the ad-hoc `species_monitoring_platform/frontend/test-*.mjs` scripts
 * and the scattered `playwright_*.txt` logs at the repo root. The legacy
 * artifacts are preserved at `_legacy/` for reference but should not be added
 * to in new work — see `README.md`.
 */

// Default points at the docker-compose-served combined app (FastAPI port 8000
// serves both the SPA static files and the /api endpoints). For a pure Vite
// dev-server run, override with E2E_SPECIES_BASE_URL=http://127.0.0.1:4000.
const SPECIES_BASE_URL = process.env.E2E_SPECIES_BASE_URL ?? 'http://127.0.0.1:8000';
const ACOUSTIC_BASE_URL = process.env.E2E_ACOUSTIC_BASE_URL ?? 'http://127.0.0.1:8001';

export default defineConfig({
  testDir: './specs',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [
    ['list'],
    ['html', { outputFolder: 'reports/html', open: 'never' }],
    ['junit', { outputFile: 'reports/junit.xml' }],
  ],
  use: {
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 10_000,
    navigationTimeout: 30_000,
  },
  projects: [
    {
      name: 'species-chromium',
      testMatch: /specs\/.*\.spec\.ts/,
      use: {
        ...devices['Desktop Chrome'],
        baseURL: SPECIES_BASE_URL,
      },
    },
  ],
  outputDir: 'reports/test-results',
});
