# Biodiversity Field Survey Platform

Biodiversity Field Survey Platform is a FastAPI + React + Capacitor application for offline-first biodiversity surveys, field sync, and jurisdiction-aware exports, with acoustic and analysis modules retained as secondary workspaces.

## Local development

Start the desktop launcher on Windows:

```bat
start_app.bat
```

Or run the backend directly:

```bash
python launcher.py
```

The default local address is:

```text
http://127.0.0.1:8000
```

Backend development:

```bash
pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Frontend development:

```bash
cd frontend
npm install
npm run dev
```

For browser and PWA development, leave `frontend/.env.local` unset or keep `VITE_API_BASE_URL=` blank so the app continues to call relative `/api` and `/ws` on the same origin.

Frontend production build:

```bash
cd frontend
npm run build
```

## Android field build

The mobile client is packaged with Capacitor from the `frontend` workspace.

Prerequisites for local Android packaging:

- JDK 21 with `JAVA_HOME` set
- Android Studio with a recent Android SDK installed
- Node dependencies installed in `frontend`

Refresh the web bundle and sync it into the Android project:

```bash
cd frontend
npm run build:android
```

Create a debug APK:

```bash
cd frontend/android
./gradlew assembleDebug
```

For field release packaging, sync the web bundle first, then configure signing in Android Studio or Gradle and build a signed release artifact from `frontend/android`.
Re-run `npm run build:android` after any field UI or offline-runtime change so the Android assets stay in sync with the web source.

Native Android builds that talk to a remote field server must set an absolute frontend API base before building:

```bash
cd frontend
cp .env.example .env.local
```

Set `VITE_API_BASE_URL` in `frontend/.env.local` to the field server origin or API root, for example `https://field.example.com` or `https://field.example.com/api`.
When this value is set, the mobile bundle uses absolute `http(s)` API calls and the matching `ws(s)` stream base.
Leave it blank for web or PWA deployments so the frontend keeps its relative `/api` and `/ws` behavior.

Health check:

```text
http://127.0.0.1:8000/api/health
```

## Field release deployment path

The current field release target is a single Docker container running on a Linux VM that is accessible to the survey team. This stays intentionally simple to operate and fits a China-friendly deployment model where the team controls its own host and network placement.

Recommended topology:

1. Provision one Ubuntu 22.04 or Debian 12 VM close to field users.
2. Install Docker Engine and Docker Compose Plugin.
3. Copy the repository to the host.
4. Copy `.env.field-release.template` to `.env` and fill in the real release values.
5. Run `deploy/release/deploy.sh`.

This deployment path keeps the backend API and built frontend in one image, uses bind-mounted persistent volumes, and exposes a single HTTP port.

## Field launch checklist

Before launch day on the VM for the Android offline-first release:

1. Confirm the repo checkout includes `backend/checkpoints/best_model.pth` and `backend/checkpoints/species_mapping.json`.
2. Copy `.env.field-release.template` to `.env`, then set `CORS_ORIGINS` to the real field client origin and review any API keys.
3. Keep the host firewall or reverse proxy restricted to field users only. Do not leave the raw HTTP port open to the public internet.
4. Run `sh deploy/release/deploy.sh` and wait for the script to report a healthy `/api/health` check.
5. Create a baseline backup before field users begin work.

## Docker field operations

Prepare environment values:

```bash
cp .env.field-release.template .env
```

The controlled go-live helper will reject blank or localhost `CORS_ORIGINS` values so the release VM is not launched with local-development settings by mistake.

The compose file separates writable field state from repo-managed model assets:

- Writable and backed up: `deploy/pilot/volumes/app-data`, `deploy/pilot/volumes/backend-data`, `deploy/pilot/volumes/config`, `deploy/pilot/volumes/logs`
- Read-only model assets: `backend/checkpoints`
- Keep `BSP_*` paths repo-relative when using the field helper scripts so backup and restore stay predictable and safe.
- The `deploy/pilot/...` directory names are retained as compatibility storage paths; use `deploy/release/...` script entrypoints for operator workflows.

Start the field stack directly:

```bash
docker compose up -d --build
```

Or use the safer helper:

```bash
sh deploy/release/deploy.sh
```

The helper script now:

- creates the writable bind-mount directories
- verifies Docker and Docker Compose are available
- validates `docker compose config`
- checks that required checkpoint files exist before startup
- waits for container health before returning success

Check service health:

```bash
curl http://127.0.0.1:8000/api/health
docker compose ps
docker compose logs --tail=100 app
```

Stop the service:

```bash
docker compose down
```

Persistent data is stored under:

- `deploy/pilot/volumes/app-data`
- `deploy/pilot/volumes/backend-data`
- `deploy/pilot/volumes/config`
- `deploy/pilot/volumes/logs`

Model checkpoints stay in:

- `backend/checkpoints`

## Backup and restore

Create a consistent backup archive:

```bash
sh deploy/release/backup.sh
```

The backup script stops the app briefly when it is running, archives the writable field volumes plus `.env`, and then restarts the app automatically.

Restore from an archive:

```bash
sh deploy/release/restore.sh --yes deploy/pilot/backups/biodiversity-field-survey-release-YYYYMMDD-HHMMSS.tar.gz
```

Restore safety notes:

- the restore script validates archive paths before extracting anything
- it creates a pre-restore safety backup unless `SKIP_PRE_RESTORE_BACKUP=1`
- it restores the current `.env` only if the host copy is missing, unless `RESTORE_ENV=1`
- it does not overwrite `backend/checkpoints`, so repo-managed model assets stay under deployment control

For field operations, schedule `deploy/release/backup.sh` with `cron` at least daily and copy the resulting archives outside the VM as well.

## Controlled Go-Live Docs

- Runbook: `docs/pilot_field_runbook.md`
- Taxonomy release runbook: `docs/taxonomy_release_runbook.md`
- Acceptance checklist: `docs/pilot_acceptance_checklist.md`
- Acceptance record template: `docs/controlled_go_live_acceptance_record.md`
- Issue log template: `docs/controlled_go_live_issue_log.md`

## CI

GitHub Actions CI is defined in `.github/workflows/ci.yml` and enforces:

- backend unit and smoke tests
- frontend tests and production build
- full Docker image build
- compose-based container health verification

## Environment variables

The main field environment values are:

- `APP_PORT`: host port mapped to the service
- `WEB_CONCURRENCY`: uvicorn worker count for the API container
- `CORS_ORIGINS`: comma-separated allowed origins
- `BIRD_API_KEY`: optional API key for protected endpoints
- `XC_API_KEY`: optional external API credential
- `BSP_APP_DATA_DIR`, `BSP_BACKEND_DATA_DIR`, `BSP_CONFIG_DIR`, `BSP_LOG_DIR`: writable host paths for field state
- `BSP_CHECKPOINTS_DIR`: read-only host path for repo-managed model files
- `BSP_HEALTH_TIMEOUT`: startup and restore health-check timeout in seconds
- `BSP_BACKUP_DIR`: destination directory for field backup archives

Frontend mobile build variable:

- `VITE_API_BASE_URL`: optional absolute base for native Capacitor builds; leave blank for browser/PWA deployments that use same-origin `/api` and `/ws`

Android release signing variables:

- `ANDROID_KEYSTORE_FILE`
- `ANDROID_KEYSTORE_PASSWORD`
- `ANDROID_KEY_ALIAS`
- `ANDROID_KEY_PASSWORD`

Use `frontend/android/release-signing.env.example` as the release-build reference and build a signed APK with `cd frontend/android && .\gradlew.bat assembleRelease` after `npm run build:android`.

## Logging and operations notes

- Application logs are written to container stdout/stderr and can be viewed with `docker compose logs`.
- Docker log rotation is enabled in `docker-compose.yml`.
- The container health check uses `/api/health`.
- Keep field deployments behind a reverse proxy, firewall allowlist, or VPN if they are not meant for open internet access.
- The compose service runs with `no-new-privileges` enabled and a longer startup health window to reduce false-negative launch failures.

## Verification commands

```bash
docker compose config -q
cd frontend && npm run build
cd frontend && npm run test
python -m unittest discover backend/tests -v
docker build -t biodiversity-field-survey:local .
docker compose up -d --build
curl http://127.0.0.1:8000/api/health
docker compose down
```
