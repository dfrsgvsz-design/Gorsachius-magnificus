# Gorsachius magnificus Research & Monitoring Workspace

Multi-project workspace for *Gorsachius magnificus* (海南鳽 / White-eared Night Heron) conservation research and field monitoring.

## Projects

### acoustic_platform
Biodiversity acoustic survey platform with real-time species detection.
- **Backend**: Python/FastAPI with CNN/BirdNet audio classification
- **Frontend**: React/Vite/Tailwind with Capacitor for mobile deployment

### species_monitoring_platform
Comprehensive species monitoring platform with extended field operations.
- **Backend**: Python/FastAPI with multi-modal survey support
- **Frontend**: React/Vite/Tailwind with field ops modules, offline sync, and GPS tracking

### project_sdm_stoten
Species Distribution Modeling (SDM) research for STOTEN journal submission.
- Analysis scripts for SDM, climate projection, and conservation gap analysis
- Manuscript preparation and submission packaging

## Setup

### Backend (both platforms)
```bash
cd <platform>/backend
pip install -r requirements.txt
python main.py
```

### Frontend (both platforms)
```bash
cd <platform>/frontend
npm install
npm run dev
```

## Architecture

Both platforms share a common set of core modules (audio processing, CNN models, taxonomy catalog, biodiversity calculations, external API clients). Platform-specific logic resides in `main.py`, `survey_store.py`, and platform-specific modules.

## Repository setup (first-time)

This workspace is a **monorepo**: the two app subdirectories plus shared
`submission/`, `scripts/`, `quality_gate.ps1`, and `.github/workflows/` are
intended to live in one git repository at the workspace root.

If you are initializing the remote for the first time:

```powershell
cd "f:\Gorsachius magnificus"
git init
git branch -M main
git add .
git commit -m "chore: initial import (monorepo: acoustic + species)"
git remote add origin https://github.com/<org>/gorsachius-magnificus.git
git push -u origin main
```

After the push, configure branch protection (Settings → Branches → Add rule
for `main`):

- Require a pull request before merging (1 approval)
- Require status check: **`Release Gate · all gates green`** (from `.github/workflows/release_gate.yml`)
- Do not allow bypassing the above settings

For Android release signing, populate these repository secrets (Settings →
Secrets and variables → Actions): `ANDROID_KEYSTORE_BASE64`,
`ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`.
Detailed flow: `submission/06_packaging_signing_runbook.md`.

## Quality gates

| Layer | Local | CI |
|---|---|---|
| Pre-commit / pre-PR sanity | `.\quality_gate.ps1` (default `-Project all`; supports `-Project acoustic\|species` and `-NoInstall`) | `.github/workflows/release_gate.yml` |
| Pre-release full verification | `.\scripts\release_gate.ps1` | `.github/workflows/release_gate.yml` on push to `main`/`master` or `v*` tag |
| Tag-time signed AAB build (species) | `submission/06_packaging_signing_runbook.md` §3 | `.github/workflows/android-release.yml` (has internal release-gate precheck) |
| App-specific container smoke | `cd <app> && docker compose up --build` | `.github/workflows/ci-acoustic.yml` / `ci-species.yml` |

Workflow file inventory and division of labor:
[`.github/workflows/README.md`](.github/workflows/README.md).

The current gate status report lives at [`QUALITY_GATE_REPORT.md`](QUALITY_GATE_REPORT.md).

