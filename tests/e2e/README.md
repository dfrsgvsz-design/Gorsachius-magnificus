# Cross-app E2E Suite

Playwright Test harness for the species_monitoring_platform 5-step critical
flow. Created 2026-06-10 (ticket #C, Batch 2). Replaces the ad-hoc
`species_monitoring_platform/frontend/test-*.mjs` scripts and the scattered
`playwright_*.txt` logs at the repo root — those are preserved under
[`_legacy/`](./_legacy/) for reference but **must not** be extended; new
specs go under [`specs/`](./specs/).

## The 5 critical steps

| # | Spec | What it asserts |
|---|---|---|
| 1 | `specs/01-app-boot.spec.ts` | SPA cold-start; sidebar nav (`总览`, `野外调查`, …) visible; no `pageerror`. |
| 2 | `specs/02-survey-protocol.spec.ts` | Field Ops tab loads; ≥ 1 project visible; protocol picker (`样线 / Transect`, `名录 / Checklist`, `样点 / Point count`, `多模态 / Multimodal`) reachable. |
| 3 | `specs/03-checkin.spec.ts` | User reaches the observation form, fills species, submit button enabled. (Granted geolocation permission for the GPS path.) |
| 4 | `specs/04-offline-submit.spec.ts` | After `context.setOffline(true)`: offline banner shown, an observation can be staged, IndexedDB `fieldsurvey` exists. |
| 5 | `specs/05-reconnect-sync.spec.ts` | After `context.setOffline(false)`: online indicator returns, outbox drains to 0 within 30 s. |

## Local run

```bash
# One-time: install browsers
cd tests/e2e
npm install
npm run install:browsers

# Run against the docker-compose-served combined app (defaults to http://127.0.0.1:8000)
npm run test

# With a Vite dev server instead of docker compose
E2E_SPECIES_BASE_URL=http://127.0.0.1:4000 npm run test

# Headed (watch the browser)
npm run test:headed

# Open the last HTML report
npm run test:report
```

Pre-flight options (pick one):

- **Dockerized (recommended, matches CI)**: `cd species_monitoring_platform && docker compose up -d` — combined FastAPI app on `http://127.0.0.1:8000` serves both `/api/*` and the built SPA static. This is what CI uses.
- **Vite dev server (faster HMR for spec authoring)**: two terminals:
  - `cd species_monitoring_platform/backend && python -m uvicorn main:app --port 8000`
  - `cd species_monitoring_platform/frontend && npm run dev -- --port 4000`
  - Then `E2E_SPECIES_BASE_URL=http://127.0.0.1:4000 npm run test` (vite proxies `/api/*` to 8000 per `vite.config`).

## CI run

GitHub Actions workflow: [`.github/workflows/e2e.yml`](../../.github/workflows/e2e.yml).

It runs on:

- Every PR that touches `species_monitoring_platform/**`, `tests/e2e/**`, or `.github/workflows/e2e.yml`
- Every push to `main`
- Manual `workflow_dispatch`

The workflow starts the backend + frontend dev server, waits for both to
respond on `/api/health` and `/`, then runs `npm run test:species`. On failure
it uploads:

- HTML report (`tests/e2e/reports/html`)
- JUnit XML (`tests/e2e/reports/junit.xml`)
- Traces + screenshots + videos (`tests/e2e/reports/test-results`)

## Why this exists

Before 2026-06-10 the test artefacts looked like this:

- 6 `playwright_*.txt` files at repo root (manual-run logs, no scripts)
- 7 `test-*.mjs` files scattered across `species_monitoring_platform/`
  and `species_monitoring_platform/frontend/` (mostly ad-hoc reconnaissance,
  not gating)
- No CI integration of any of the above
- Per QUALITY_GATE_REPORT.md, no E2E layer was running anywhere

The ticket #C P0 W1 second item required "整合零散脚本为 tests/e2e/ 目录,
跑在 GitHub Actions 上, 至少跑通登录 → 选调查协议 → 打点 → 离线提交 →
重连同步 5 步". This directory IS that integration.

## Maintenance guide

Selectors in these specs are **testid-first** (see taxonomy below). All five
specs use `page.getByTestId(...)` for navigation, prep flow, observation
form, and sync controls. When a spec breaks for UI-copy reasons that means
the testid was removed or renamed — fix in the SPA source, not in the spec.

### Testid taxonomy (all currently in place as of 2026-06)

| Surface | testid | Source |
|---|---|---|
| Sidebar nav button | `nav-tab-<tab-id>` (e.g., `nav-tab-fieldops`) with `data-active="true\|false"` | `species/frontend/src/App.jsx` |
| Sidebar footer status dot | `app-status-dot` with `data-state="online\|connecting\|offline"` | `species/frontend/src/App.jsx` |
| Step tab inside FieldOps | `step-tab-<id>` (`setup` / `survey` / `records`) with `data-active` | `species/frontend/src/components/tabs/FieldOpsTab.jsx` |
| Top-right online indicator | `network-chip` with `data-state="online\|offline"` | `species/frontend/src/components/tabs/FieldOpsTab.jsx` |
| Top-right sync controls | `sync-pull`, `sync-push` (`sync-push` also has `data-pending-count`) | `species/frontend/src/components/tabs/FieldOpsTab.jsx` |
| Setup level header (h2) | `setup-level-header` with `data-level="projects\|sites\|routes"` | `species/frontend/src/components/tabs/FieldOpsTab.jsx` |
| Project / Site / Route row | `project-row-<id>` / `site-row-<id>` / `route-row-<id>` (each with `data-active`) | `species/frontend/src/components/tabs/FieldOpsTab.jsx` |
| Prep observer input | `prep-observer` | `species/frontend/src/components/tabs/FieldOpsTab.jsx` |
| Prep weather input | `prep-weather` | `species/frontend/src/components/tabs/FieldOpsTab.jsx` |
| Prep "Start Survey" button | `prep-start` | `species/frontend/src/components/tabs/FieldOpsTab.jsx` |
| Survey "End" button | `survey-end` | `species/frontend/src/components/tabs/FieldOpsTab.jsx` |
| Observation FAB (round + / camera) | `obs-fab` | `species/frontend/src/components/tabs/FieldOpsTab.jsx` |
| Observation form species autocomplete | `obs-species-input` | `species/frontend/src/components/fieldops/ComboField.jsx` (`SpeciesAutocomplete`) |
| Observation save button | `obs-submit` | `species/frontend/src/components/fieldops/ObservationFormPanel.jsx` |
| Sync panel pending count chip | `sync-pending-count` with `data-count` | `species/frontend/src/components/fieldops/SyncPanel.jsx` |

When adding new specs:

1. Pick a stable signal. Prefer `data-state` / `data-active` / `data-count`
   attributes (numeric / enum), not visible text, for assertions.
2. If no testid exists for what you need, add one to the SPA source first,
   then write the spec. Do not rely on `getByText` for new specs.
3. Use kebab-case testids, scoped by surface (e.g., `obs-*` for observation
   form, `sync-*` for sync controls, `prep-*` for the prep panel,
   `nav-tab-*` for sidebar nav).

## Legacy directory

[`_legacy/`](./_legacy/) holds the 12 historical artifacts. Read its
`README.md` for a per-file accounting of origin and what each one was used
for. Do not extend `_legacy/`; if you need a new test, add a `specs/` entry.
