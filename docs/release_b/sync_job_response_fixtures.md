# `sync_job` backend fixtures · response shapes B can mock

**Date**: 2026-06-10
**Audience**: 工程师 B（前端 / sync engine）
**Backend source of truth**: `shared/backend/stores/survey_store.py::sync_push:6015`
**Route**: `POST /api/surveys/sync/push`

B asked for a backend fixture so the React side can mock-test the
`useSyncEngine` happy/conflict/partial paths without spinning the full
FastAPI lifespan. This file inlines representative responses; copy any
of them into `frontend/src/__fixtures__/sync_job.fixture.json` (or
wherever B's mock conventions land).

The wire-level wrapper from `routes/survey.py::push_field_sync` always
looks like `{ "status": "ok", "sync_job": <SYNC_JOB> }` even when the
underlying `sync_job.status` is `"conflict"` (HTTP-level wrapper is OK;
the per-job status drives client behaviour).

## A) All operations applied cleanly

```json
{
  "status": "ok",
  "sync_job": {
    "sync_job_id": "sync_5p8x2qg1a3z4n",
    "device_id": "android-pixel-7a-001",
    "user_id": "field.lead@example.org",
    "status": "applied",
    "operation_count": 3,
    "applied_count": 3,
    "deleted_count": 0,
    "conflict_count": 0,
    "created_at": "2026-06-10T08:13:42.117000Z",
    "updated_at": "2026-06-10T08:13:42.453000Z",
    "applied": [
      {
        "entity_type": "project",
        "record": {
          "project_id": "proj_8gx1q2",
          "name": "Hainan 2026Q2 prelim",
          "region": "guangxi-jingxi",
          "updated_at": "2026-06-10T08:13:42.301000Z",
          "sync_state": "synced"
        }
      },
      {
        "entity_type": "site",
        "record": {
          "site_id": "site_5n3vq8",
          "project_id": "proj_8gx1q2",
          "name": "Site 03 · Gorsachius hotspot",
          "latitude": 24.6321,
          "longitude": 110.4087,
          "sensitivity": "masked_10km",
          "sync_state": "synced",
          "updated_at": "2026-06-10T08:13:42.317000Z"
        }
      },
      {
        "entity_type": "observation",
        "record": {
          "observation_id": "obs_4kz1q7",
          "project_id": "proj_8gx1q2",
          "site_id": "site_5n3vq8",
          "scientific_name": "Gorsachius magnificus",
          "count": 1,
          "evidence_type": "visual",
          "observed_at": "2026-06-10T05:51:00Z",
          "sync_state": "synced"
        }
      }
    ],
    "deleted": [],
    "conflicts": []
  }
}
```

## B) Partial · 2 applied, 1 conflicted

```json
{
  "status": "ok",
  "sync_job": {
    "sync_job_id": "sync_9p1z3qa4b7c2y",
    "device_id": "android-pixel-7a-001",
    "user_id": "field.lead@example.org",
    "status": "partial",
    "operation_count": 3,
    "applied_count": 2,
    "deleted_count": 0,
    "conflict_count": 1,
    "created_at": "2026-06-10T08:18:01.444000Z",
    "updated_at": "2026-06-10T08:18:01.812000Z",
    "applied": [
      { "entity_type": "project", "record": { "project_id": "proj_8gx1q2", "...": "trimmed" } },
      { "entity_type": "site",    "record": { "site_id":    "site_5n3vq8",  "...": "trimmed" } }
    ],
    "deleted": [],
    "conflicts": [
      {
        "conflict_id": "conflict_2vqx7m",
        "sync_job_id": "sync_9p1z3qa4b7c2y",
        "entity_type": "observation",
        "entity_id": "obs_4kz1q7",
        "status": "open",
        "created_at": "2026-06-10T08:18:01.812000Z",
        "updated_at": "2026-06-10T08:18:01.812000Z",
        "fields": ["count", "confidence"],
        "incoming": {
          "observation_id": "obs_4kz1q7",
          "project_id": "proj_8gx1q2",
          "site_id": "site_5n3vq8",
          "scientific_name": "Gorsachius magnificus",
          "count": 2,
          "confidence": 0.85,
          "observed_at": "2026-06-10T05:51:00Z",
          "sync_state": "pending"
        },
        "server": {
          "observation_id": "obs_4kz1q7",
          "project_id": "proj_8gx1q2",
          "site_id": "site_5n3vq8",
          "scientific_name": "Gorsachius magnificus",
          "count": 1,
          "confidence": 0.92,
          "observed_at": "2026-06-10T05:51:00Z",
          "updated_at": "2026-06-09T22:00:14.117000Z",
          "sync_state": "synced"
        }
      }
    ]
  }
}
```

UI invariant for `partial`: render the 2 applied entries as success +
surface the single conflict in the conflict-resolution drawer. Do NOT
treat the whole job as failed.

## C) Conflict · all 1 operation rejected

```json
{
  "status": "ok",
  "sync_job": {
    "sync_job_id": "sync_3a8m1qz5b2c7r",
    "device_id": "android-pixel-7a-001",
    "user_id": "field.lead@example.org",
    "status": "conflict",
    "operation_count": 1,
    "applied_count": 0,
    "deleted_count": 0,
    "conflict_count": 1,
    "created_at": "2026-06-10T08:22:09.555000Z",
    "updated_at": "2026-06-10T08:22:09.901000Z",
    "applied": [],
    "deleted": [],
    "conflicts": [
      {
        "conflict_id": "conflict_7g2v9k",
        "sync_job_id": "sync_3a8m1qz5b2c7r",
        "entity_type": "site",
        "entity_id": "site_5n3vq8",
        "status": "open",
        "created_at": "2026-06-10T08:22:09.901000Z",
        "updated_at": "2026-06-10T08:22:09.901000Z",
        "fields": ["latitude", "longitude", "sensitivity"],
        "incoming": {
          "site_id": "site_5n3vq8",
          "project_id": "proj_8gx1q2",
          "name": "Site 03 · Gorsachius hotspot",
          "latitude": 24.6499,
          "longitude": 110.4123,
          "sensitivity": "public",
          "sync_state": "pending"
        },
        "server": {
          "site_id": "site_5n3vq8",
          "project_id": "proj_8gx1q2",
          "name": "Site 03 · Gorsachius hotspot",
          "latitude": 24.6321,
          "longitude": 110.4087,
          "sensitivity": "masked_10km",
          "updated_at": "2026-06-10T08:21:45.012000Z",
          "sync_state": "synced"
        }
      }
    ]
  }
}
```

UI invariant for `conflict`: queue stays at length 1 (user hasn't
chosen) but `syncMeta.lastStatus` should NOT flip to `'error'` — the
push call itself succeeded with 200. Use a distinct status, e.g.
`'pending_conflict'`, to keep the e2e double-assertion in
`sync_engine_exception_audit.md::Fix C` clean.

## D) Delete operation · idempotent

```json
{
  "status": "ok",
  "sync_job": {
    "sync_job_id": "sync_6e2p5qk0v9d1z",
    "device_id": "android-pixel-7a-001",
    "user_id": "field.lead@example.org",
    "status": "applied",
    "operation_count": 1,
    "applied_count": 0,
    "deleted_count": 1,
    "conflict_count": 0,
    "created_at": "2026-06-10T08:25:33.220000Z",
    "updated_at": "2026-06-10T08:25:33.412000Z",
    "applied": [],
    "deleted": [
      { "entity_type": "observation", "entity_id": "obs_4kz1q7" }
    ],
    "conflicts": []
  }
}
```

DELETE is soft (B19/B21): the row is tombstoned in `survey_trash` and
can be restored within `SURVEY_TRASH_RETENTION_DAYS` via
`POST /api/surveys/observations/{id}/restore`. Re-deleting an already-
deleted entity is a no-op (`deleted_count` stays at 0).

## Field-by-field schema reference

| Field | Type | Stability | Notes |
|---|---|---|---|
| `sync_job.sync_job_id` | str | stable | format `sync_<base32>`, primary key in `survey_sync_jobs` |
| `sync_job.device_id` | str | stable | echo of request payload |
| `sync_job.user_id` | str | stable | echo of request payload |
| `sync_job.status` | str | stable | `"applied" \| "partial" \| "conflict"` |
| `sync_job.operation_count` | int | stable | how many ops we tried |
| `sync_job.applied_count` | int | stable | ops that hit the DB |
| `sync_job.deleted_count` | int | stable | ops that tombstoned a row |
| `sync_job.conflict_count` | int | stable | ops that landed in `survey_sync_conflicts` |
| `sync_job.created_at` / `updated_at` | str (ISO-8601 UTC) | stable | server timestamps |
| `sync_job.applied[].entity_type` | str | stable | one of project, site, route, observation, track, event, design_asset, map_package |
| `sync_job.applied[].record` | object | **shape-stable per entity_type** | the persisted row — same shape that `/api/surveys/sync/pull` returns |
| `sync_job.deleted[].entity_type` / `entity_id` | str | stable | minimal; full row is gone |
| `sync_job.conflicts[].conflict_id` | str | stable | format `conflict_<base32>`, primary key in `survey_sync_conflicts` |
| `sync_job.conflicts[].fields` | str[] | stable | the field names whose `incoming` and `server` values differ — render these field-by-field in the drawer |
| `sync_job.conflicts[].incoming` | object | shape-stable per entity_type | client payload as received |
| `sync_job.conflicts[].server` | object | shape-stable per entity_type | server's current row |

Whenever the schema changes, this doc + the backend test in
`tests/test_survey_store.py::test_sync_push_*` move together (they
share the same module under test).
