# GitHub Actions Workflows

Single source of truth for CI/CD. All workflows live at the **repo root**
`.github/workflows/` so GitHub Actions actually discovers them.

> Historical note: prior to 2026-06 the workflows were scattered under
> `acoustic_platform/.github/workflows/` and `species_monitoring_platform/.github/workflows/`.
> Those locations are NOT picked up by GitHub Actions (only the repo root is)
> and have been migrated here. Do not put workflow YAML in subdirectories.

## Workflow inventory

| Workflow | Triggers | Scope | Purpose |
|---|---|---|---|
| `release_gate.yml` | PR to `main`/`master`, push to `main`/`master`, `v*` tag, manual | Both apps (matrix) | **The PR-required gate.** Backend critical tests + frontend lint/build for both apps. On push/tag, also runs full pytest suite with coverage. Aggregate job `Release Gate · all gates green` is the check to require in branch protection. |
| `e2e.yml` | PR/push touching `species_monitoring_platform/**`, `tests/e2e/**`, or `e2e.yml` itself; manual | species_monitoring_platform (5-step critical flow) | Brings up species docker-compose stack on `:8000`, runs Playwright Test against the 5 specs in `tests/e2e/specs/` (app boot / survey protocol / checkin / offline submit / reconnect sync). Uploads HTML report, JUnit, traces, screenshots, videos. |
| `ci-acoustic.yml` | PR/push touching `acoustic_platform/**` | acoustic_platform only | Full backend test suite (`pytest tests -q`) + frontend test + container verification (`docker compose up` + health check). |
| `ci-species.yml` | PR/push touching `species_monitoring_platform/**` | species_monitoring_platform only | Same as ci-acoustic but for species. |
| `android-release.yml` | `v*` tag, manual | species_monitoring_platform | Tag-driven signed AAB+APK build for Play Store. Has its own internal `release-gate` job that mirrors `release_gate.yml`'s critical subset before the `signed-release` job; tags that don't pass the gate cannot publish artefacts. Requires `ANDROID_KEYSTORE_*` secrets. |

## Division of labor

- **PR-time confidence**: `release_gate.yml` is the cheap, fast cross-app gate
  that must pass before any PR merges. Tighten branch protection to require its
  `Release Gate · all gates green` aggregate check.
- **Push/main confidence**: `ci-acoustic.yml` and `ci-species.yml` add
  app-specific full test runs and container-startup smoke tests (heavier than
  the PR gate, runs only on the relevant app's changes).
- **Tag-time release confidence**: `android-release.yml` re-runs the critical
  subset of the gate inline, then signs and uploads artefacts. This double
  check is deliberate: it ensures the artefact you ship was built from a
  green commit, even if branch protection was bypassed.
- **End-to-end confidence**: `e2e.yml` is the only workflow that exercises
  the species SPA inside a real browser against a real backend. Treat its
  reports as the canonical answer to "would a user be able to do their job
  today?" — when it fails, look at the uploaded HTML report and trace first.

## Local equivalents

| Workflow | Local equivalent |
|---|---|
| `release_gate.yml` (PR-time subset) | `powershell -ExecutionPolicy Bypass -File .\quality_gate.ps1` |
| `release_gate.yml` (push/tag full subset) | `powershell -ExecutionPolicy Bypass -File .\scripts\release_gate.ps1` |
| `ci-acoustic.yml` container job | `cd acoustic_platform && docker compose up --build` |
| `ci-species.yml` container job | `cd species_monitoring_platform && docker compose up --build` |
| `e2e.yml` | See `tests/e2e/README.md` — `cd tests/e2e && npm install && npm run test` (against a running stack) |
| `android-release.yml` | See `submission/06_packaging_signing_runbook.md` §3 |

## Required repository secrets

For `android-release.yml`:

- `ANDROID_KEYSTORE_BASE64` — base64 of `species-monitoring-release.jks`
- `ANDROID_KEYSTORE_PASSWORD` — keystore password (from Vault, not on disk)
- `ANDROID_KEY_ALIAS` — `speciesmonitoring-release`
- `ANDROID_KEY_PASSWORD` — key password (PKCS12, same as keystore)

Set these under repo Settings → Secrets and variables → Actions.

## Branch protection (recommended)

Under repo Settings → Branches → Add rule for `main`:

- Branch name pattern: `main`
- Require a pull request before merging: enabled
  - Require approvals: 1
- Require status checks to pass before merging: enabled
  - Required: `Release Gate · all gates green`
  - (Optional but recommended) Also require: `ci-acoustic / container-verification`, `ci-species / container-verification` for affected paths.
- Do not allow bypassing the above settings: enabled

## When to edit a workflow

- Adding a new test dimension that should gate every PR → edit `release_gate.yml`.
- Adding an app-specific heavy test (e.g., GPU model regression for acoustic) →
  edit `ci-acoustic.yml` / `ci-species.yml`.
- Changing how the signed AAB is produced → edit `android-release.yml`.
- New workflow for a new concern (e.g., scheduled deps audit) → add a new file
  here, do NOT put it in a subdirectory.
