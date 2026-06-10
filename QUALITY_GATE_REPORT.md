> **Note**: This report was last regenerated on **2026-06-10** as part of ticket #C
> Batch 1 (P0 W1). The previous 2026-04-24 P0 (`No module named pytest`) was
> caused by `quality_gate.ps1` invoking pytest **without ever installing it**;
> this is fixed at the source — see "Remediation" below.
>
> Re-run the gate locally to verify:
> `powershell -ExecutionPolicy Bypass -File "f:\Gorsachius magnificus\quality_gate.ps1"`

# Quality Gate Report (both apps)

## Scope

- Apps in scope: `acoustic_platform` AND `species_monitoring_platform`
- Local gate script: `quality_gate.ps1` (defaults to `-Project all`)
- Local release script: `scripts/release_gate.ps1`
- CI gate: `.github/workflows/release_gate.yml`
  (matrix over both apps; PR-required; tag-required for android-release)
- Gate dimensions:
  1. Backend dependency install (runtime + dev) — Step 0
  2. Backend syntax check (`python -m compileall .`)
  3. Backend lint (`ruff check . --select E9,F63,F7,F82`)
  4. Frontend lint (`npm run lint`)
  5. Frontend production build (`npm run build`)
  6. Backend critical tests (smoke / runtime / realtime)

## Execution commands

| Scope | Command |
|---|---|
| Both apps end-to-end (default) | `powershell -ExecutionPolicy Bypass -File "f:\Gorsachius magnificus\quality_gate.ps1"` |
| Single app | `quality_gate.ps1 -Project acoustic` or `-Project species` |
| Legacy abs-path mode | `quality_gate.ps1 -ProjectRoot "<abs path>"` |
| Skip install (warm env) | `quality_gate.ps1 -NoInstall` |
| Full release verification | `powershell -ExecutionPolicy Bypass -File "scripts\release_gate.ps1"` |

## Latest expected run result (2026-06-10, post-remediation)

After Batch 1 changes the gate sequence is:

| Step | Status target | Notes |
|---|---|---|
| **NEW** Step 0: install runtime + dev deps | PASS | `pip install -r requirements.txt -r requirements-dev.txt` |
| Backend syntax check (`python -m compileall .`) | PASS | unchanged |
| Backend lint (ruff E9/F63/F7/F82) | PASS | unchanged |
| Frontend lint (`npm run lint`) | PASS | unchanged |
| Frontend build (`npm run build`) | PASS | unchanged |
| Backend critical tests (3 files) | PASS | previously FAIL (no pytest); now resolved |

Overall expected gate result: **PASS** (pending local dev verification).

## P0 / P1 defect status

### P0

1. ~~**Testing runtime missing critical dependency (`pytest`)**~~ — **RESOLVED (2026-06-10)**
   - Root cause: `quality_gate.ps1` had no install step; relied on ambient venv.
   - Remediation:
     - Created `acoustic_platform/backend/requirements-dev.txt` and
       `species_monitoring_platform/backend/requirements-dev.txt` with pinned
       `pytest>=8`, `pytest-asyncio`, `pytest-cov`, `ruff`, `httpx`.
     - Removed `pytest` / `pytest-asyncio` from both `requirements.txt` and from
       `species_monitoring_platform/deploy/staging/backend/requirements.txt`
       so production images no longer ship test code dependencies.
     - `quality_gate.ps1` now runs `pip install -r requirements.txt -r requirements-dev.txt`
       as Step 0 for each gated app.
     - `scripts/release_gate.ps1` switched from `python -m unittest` to pytest
       and now installs the same dev deps.
     - `.github/workflows/release_gate.yml` (new, repo-root) replicates the
       same gate sequence for PRs and tags, with a matrix over both apps.

### P1

1. ~~**Backend test dependencies not explicitly separated/documented**~~ — **RESOLVED (2026-06-10)**
   - `requirements-dev.txt` now exists for both apps, listed in `ci.yml` cache
     keys, and referenced by both `.ps1` gates and the GitHub Actions workflow.

## B-side complementary gates (2026-06 additions)

The following B-contributed pieces are now in tree and complement C's gates:

| File | Provides |
|---|---|
| `release_gate.yml` `runtime-contract-gate` job (B) | Repo-wide assertion that `describe_runtime_paths()` returns all `*_externalized` flags True + `platform_config.json` loads. Catches accidental demo-mode regressions before any other gate runs. |
| `scripts/pressure_test_projects.py` (B) | 200×sequential POST `/api/surveys/projects` via FastAPI TestClient (full lifespan). Asserts no 503/500 + every response has `X-Request-ID`. Wired into `release_gate.yml` `backend-gate` as the no-503 SLO step. |
| `scripts/smoke_production_health.sh` (B) | 1-line production smoke against `https://swdyx.eu.cc` + `https://acoustic.swdyx.eu.cc` covering DNS, cert, all 3 health endpoints, readiness.mode=production, runtime_paths.mutable_runtime_externalized. |
| `scripts/archive_mapping.ps1` (B) | One-line mapping archive per release. Path-reconciled with `scripts/deobfuscate.ps1` (-VersionName fallback) — see `submission/_mapping_archive/README.md`. |
| `docs/release_b/2026-06-10_production_deploy_runbook.md` (B) | Production deployment SOP (domains, DNS, LE, Sentry, 24h SLO probe crontab). Referenced by `submission/governance/rollback_sop_v1.md` §1 and §8. |
| `docs/release_b/play_app_signing_4_steps.md` (B) | PM-facing Play App Signing 4-step checklist with dual-sign. Referenced by `submission/06_packaging_signing_runbook.md` §2.1. |
| `docs/release_b/sync_engine_exception_audit.md` (B) | Audit of `useSyncEngine` exception paths. The `sync-push` `data-status` attribute + spec 05's triple assertion came out of this audit. |
| `docs/release_b/sync_job_response_fixtures.md` (B) | 4 canonical sync_job JSON responses (applied / partial / conflict / delete) with schema doc. |
| `docs/release_b/2026-06-10_422_503_inventory.md` (B) | Cross-team SLO inventory of 422/503 endpoints. |
| `docs/release_b/data_testid_regression_audit.md` (B) | Visual-regression audit of the 18 testid additions C made (App.jsx + FieldOpsTab.jsx + ComboField.jsx + ObservationFormPanel.jsx + SyncPanel.jsx). |
| `docs/release_b/playstore_foreground_service_rationale.md` (B) | Android 14+ `FOREGROUND_SERVICE_LOCATION/MICROPHONE` declaration rationale for Play Console review. |

## Outstanding architectural notes

1. ~~**Per-app `.github/workflows/` directories may not run**~~ — **RESOLVED
   (2026-06-10, Batch 1 follow-up A)**. All workflows hoisted to repo root
   `.github/workflows/`:
   - `acoustic_platform/.github/workflows/ci.yml` → root `ci-acoustic.yml` (paths re-rooted)
   - `species_monitoring_platform/.github/workflows/ci.yml` → root `ci-species.yml`
   - `species_monitoring_platform/.github/workflows/android-release.yml` → root `android-release.yml`
   - New cross-app gate: root `release_gate.yml`
   - Workflow inventory + division of labor: `.github/workflows/README.md`

2. **Workspace is not yet under version control** (NEW finding, 2026-06-10).
   No `.git/` exists at workspace root or in either app subdir. The CI
   workflows are correct templates but will only run after `git init` + push
   to GitHub. First-time setup steps: see root `README.md` → "Repository setup
   (first-time)".

3. **Branch protection is not yet enforced**. After release_gate.yml is
   verified green on a real PR, configure repo Settings → Branches → `main`:
   - Required status check: `Release Gate · all gates green`
   - Require PR review before merge (1 approval)
   - Do not allow bypassing the above settings

## File trail

| File | Action |
|---|---|
| `acoustic_platform/backend/requirements-dev.txt` | NEW |
| `species_monitoring_platform/backend/requirements-dev.txt` | NEW |
| `acoustic_platform/backend/requirements.txt` | removed pytest / pytest-asyncio |
| `species_monitoring_platform/backend/requirements.txt` | removed pytest / pytest-asyncio |
| `species_monitoring_platform/deploy/staging/backend/requirements.txt` | removed pytest / pytest-asyncio |
| `acoustic_platform/.github/workflows/ci.yml` | install dev deps; switch unittest → pytest; **then DELETED (migrated)** |
| `species_monitoring_platform/.github/workflows/ci.yml` | install dev deps; tighten pytest flags; **then DELETED (migrated)** |
| `species_monitoring_platform/.github/workflows/android-release.yml` | added `release-gate` job; **then DELETED (migrated)** |
| `quality_gate.ps1` | path-agnostic; `-Project all\|acoustic\|species`; Step 0 install |
| `scripts/release_gate.ps1` | path-agnostic; install + pytest unification |
| `.github/workflows/release_gate.yml` | NEW — repo-root PR/tag gate (matrix over both apps) |
| `.github/workflows/ci-acoustic.yml` | NEW — migrated from acoustic_platform, paths re-rooted, `paths:` filter added |
| `.github/workflows/ci-species.yml` | NEW — migrated from species_monitoring_platform, paths re-rooted, `paths:` filter added |
| `.github/workflows/android-release.yml` | NEW — migrated from species_monitoring_platform, paths re-rooted |
| `.github/workflows/README.md` | NEW — workflow inventory + division of labor + branch-protection setup |
| `README.md` | added "Repository setup (first-time)" + "Quality gates" sections |
