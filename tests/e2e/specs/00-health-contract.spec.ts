import { test, expect, request } from '@playwright/test';

/**
 * Step 0/5 — production health contract.
 *
 * Locks the /api/health response shape that A guarantees in their reply to
 * C's coordination message (2026-06). The contract is also enforced by
 * `species_monitoring_platform/backend/tests/test_health_runtime.py` —
 * this spec is the cross-cut check that protects the SPA's runtime guards
 * (e.g. App.jsx:264-288 consume status / runtime_state / model.version /
 * num_species_model).
 *
 * If A ever changes the contract, BOTH this spec AND `test_health_runtime.py`
 * must move in lockstep. The reply that defined this contract is captured
 * in QUALITY_GATE_REPORT.md "Outstanding architectural notes" §4.
 */
test.describe('00 - production /api/health contract', () => {
  test('all three health endpoints satisfy the production gate', async ({ request: req, baseURL }) => {
    const base = baseURL ?? 'http://127.0.0.1:8000';

    const liveness = await req.get(`${base}/api/health/liveness`);
    expect(liveness.ok(), `liveness returned ${liveness.status()}`).toBe(true);
    expect(await liveness.json()).toMatchObject({ status: 'alive' });

    const readinessResp = await req.get(`${base}/api/health/readiness`);
    expect(readinessResp.ok(), `readiness returned ${readinessResp.status()}`).toBe(true);
    const readiness = await readinessResp.json();
    expect(readiness.status, 'readiness.status').toBe('ok');
    expect(readiness.ready, 'readiness.ready').toBe(true);
    expect(readiness.deployment_ready, 'readiness.deployment_ready').toBe(true);
    expect(readiness.runtime_state, 'readiness.runtime_state').toBe('ready');
    expect(readiness.model_loaded, 'readiness.model_loaded').toBe(true);
    expect(readiness.survey_store_ready, 'readiness.survey_store_ready').toBe(true);
    expect(readiness.detection_store_ready, 'readiness.detection_store_ready').toBe(true);

    const healthResp = await req.get(`${base}/api/health`);
    expect(healthResp.ok(), `health returned ${healthResp.status()}`).toBe(true);
    const health = await healthResp.json();

    expect(health.status, 'health.status').toBe('ok');
    expect(health.runtime_state, 'health.runtime_state').toBe('ready');
    expect(health.deployment_ready, 'health.deployment_ready').toBe(true);

    expect(health.readiness, 'health.readiness payload').toBeTruthy();
    expect(health.readiness.mode, 'readiness.mode must be production').toBe('production');
    expect(health.readiness.blocking_codes, 'readiness.blocking_codes must be empty').toEqual([]);
    expect(health.readiness.checks?.model_loaded, 'checks.model_loaded').toBe(true);
    expect(health.readiness.checks?.runtime_state_ready, 'checks.runtime_state_ready').toBe(true);
    expect(health.readiness.checks?.mutable_runtime_externalized, 'checks.mutable_runtime_externalized').toBe(true);

    expect(health.runtime_paths, 'runtime_paths payload').toBeTruthy();
    for (const key of [
      'data_dir_externalized',
      'checkpoints_dir_externalized',
      'frontend_dist_dir_externalized',
      'mutable_runtime_externalized',
    ]) {
      expect(
        health.runtime_paths[key],
        `runtime_paths.${key} must be true (anti-demo gate)`,
      ).toBe(true);
    }

    expect(health.survey_readiness, 'survey_readiness payload').toBeTruthy();
    expect(health.survey_readiness.deployment_ready, 'survey_readiness.deployment_ready').toBe(true);

    expect(typeof health.current_taxonomy_release_id, 'current_taxonomy_release_id should be a string').toBe('string');
    expect(health.current_taxonomy_release_id.length, 'taxonomy_release_id non-empty').toBeGreaterThan(0);
  });
});
