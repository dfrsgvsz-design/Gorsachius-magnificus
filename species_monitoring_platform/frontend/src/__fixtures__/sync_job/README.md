# `sync_job` response fixtures

Backend-authored response shapes for `POST /api/surveys/sync/push`, copied
verbatim from `docs/release_b/sync_job_response_fixtures.md` (Team A,
2026-06-10). Use these to drive `useSyncEngine` / `applySyncResult` tests
without standing up the FastAPI lifespan.

| File | Backend `sync_job.status` | What it exercises |
|---|---|---|
| `applied.json` | `applied` | 3 ops succeed, queue drains fully |
| `partial.json` | `partial` | 2 applied + 1 conflicted, queue partially drains |
| `conflict.json` | `conflict` | 1 op rejected, queue stays (item gets `queue_status: 'conflict'` marker) |
| `delete.json` | `applied` | tombstone path; `deleted[]` populated, `applied[]` empty |

Whenever team A bumps the backend schema, both
`docs/release_b/sync_job_response_fixtures.md` and these JSON files move
together. The `tests/test_survey_store.py::test_sync_push_*` suite on the
backend pins the same shapes.

The wire-level envelope is always `{ "status": "ok", "sync_job": <...> }` —
even when `sync_job.status === "conflict"` the HTTP layer is still 200.
The frontend mock should strip the outer envelope before passing to
`applySyncResult(state, sync_job)`.
