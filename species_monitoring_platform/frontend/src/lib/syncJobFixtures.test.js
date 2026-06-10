import { afterEach, describe, expect, it } from 'vitest'
import { applySyncResult, emptySurveyState, upsertLocalEntity } from './surveyOffline'

import appliedFixture from '../__fixtures__/sync_job/applied.json'
import partialFixture from '../__fixtures__/sync_job/partial.json'
import conflictFixture from '../__fixtures__/sync_job/conflict.json'
import deleteFixture from '../__fixtures__/sync_job/delete.json'

// Replay each authoritative backend fixture (provided by team A in
// `docs/release_b/sync_job_response_fixtures.md`) against the frontend
// reducer so a schema drift on either side surfaces here loudly instead of
// quietly miscoloring the conflict drawer / sync chip in production.

function localStorageStub() {
  const storage = new Map()
  return {
    getItem: (key) => (storage.has(key) ? storage.get(key) : null),
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: (key) => storage.delete(key),
    clear: () => storage.clear(),
  }
}

function withQueuedOps(ops) {
  globalThis.window = { localStorage: localStorageStub() }
  let state = emptySurveyState()
  for (const op of ops) {
    state = upsertLocalEntity(state, op.entity_type, op.payload, { queue: true })
  }
  return state
}

afterEach(() => {
  delete globalThis.window
})

describe('applySyncResult vs backend sync_job fixtures', () => {
  it('Fixture A — all applied: queue drains fully, lastStatus=synced, no conflicts', () => {
    const state = withQueuedOps([
      { entity_type: 'project', payload: { project_id: 'proj_8gx1q2', name: 'Hainan 2026Q2 prelim' } },
      { entity_type: 'site', payload: { site_id: 'site_5n3vq8', project_id: 'proj_8gx1q2', latitude: 24.6321, longitude: 110.4087 } },
      { entity_type: 'observation', payload: { observation_id: 'obs_4kz1q7', project_id: 'proj_8gx1q2', site_id: 'site_5n3vq8', count: 1 } },
    ])
    expect(state.syncQueue.length).toBe(3)

    const next = applySyncResult(state, appliedFixture.sync_job)

    // User-facing invariants: the four signals the e2e 05 quad-assertion
    // depends on.
    expect(next.syncQueue.length).toBe(0)
    expect(next.conflicts).toEqual([])
    expect(next.syncMeta.lastStatus).toBe('synced')
    expect(next.syncMeta.lastPushedAt).toBe(appliedFixture.sync_job.updated_at)
    // The observation row stays present (regardless of internal sync_state
    // — `chooseLatest` keeps the existing local timestamp when the server
    // response omits `updated_at`, which is intentional and unrelated to
    // the "did the push succeed" question this test owns).
    expect(next.observations.some((o) => o.observation_id === 'obs_4kz1q7')).toBe(true)
  })

  it('Fixture B — partial: queue drains the 2 applied, keeps the conflict, lastStatus=conflict', () => {
    const state = withQueuedOps([
      { entity_type: 'project', payload: { project_id: 'proj_8gx1q2' } },
      { entity_type: 'site', payload: { site_id: 'site_5n3vq8', project_id: 'proj_8gx1q2', latitude: 24.6321, longitude: 110.4087 } },
      { entity_type: 'observation', payload: { observation_id: 'obs_4kz1q7', project_id: 'proj_8gx1q2', site_id: 'site_5n3vq8', count: 2 } },
    ])
    expect(state.syncQueue.length).toBe(3)

    const next = applySyncResult(state, partialFixture.sync_job)

    expect(next.syncQueue.length).toBe(1)
    expect(next.syncQueue[0].entity_id).toBe('obs_4kz1q7')
    expect(next.syncQueue[0].queue_status).toBe('conflict')
    expect(next.conflicts).toHaveLength(1)
    expect(next.conflicts[0].conflict_id).toBe('conflict_2vqx7m')
    expect(next.syncMeta.lastStatus).toBe('conflict')
  })

  it('Fixture C — all conflict: queue intact with conflict marker, lastStatus=conflict', () => {
    const state = withQueuedOps([
      { entity_type: 'site', payload: { site_id: 'site_5n3vq8', project_id: 'proj_8gx1q2', latitude: 24.6499, longitude: 110.4123 } },
    ])
    expect(state.syncQueue.length).toBe(1)

    const next = applySyncResult(state, conflictFixture.sync_job)

    expect(next.syncQueue.length).toBe(1)
    expect(next.syncQueue[0].entity_id).toBe('site_5n3vq8')
    expect(next.syncQueue[0].queue_status).toBe('conflict')
    expect(next.conflicts).toHaveLength(1)
    expect(next.conflicts[0].entity_type).toBe('site')
    expect(next.syncMeta.lastStatus).toBe('conflict')
  })

  it('Fixture D — delete (tombstone): queue drains, lastStatus=synced, no conflicts', () => {
    const state = withQueuedOps([
      { entity_type: 'observation', payload: { observation_id: 'obs_4kz1q7', project_id: 'proj_8gx1q2', site_id: 'site_5n3vq8' } },
    ])
    expect(state.syncQueue.length).toBe(1)

    const next = applySyncResult(state, deleteFixture.sync_job)

    expect(next.syncQueue.length).toBe(0)
    expect(next.conflicts).toEqual([])
    expect(next.syncMeta.lastStatus).toBe('synced')
  })
})
