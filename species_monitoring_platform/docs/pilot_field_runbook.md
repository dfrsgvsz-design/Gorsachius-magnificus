# Android Offline-First Biodiversity Field Runbook

## Purpose

This runbook covers the staged field release for the biodiversity survey platform.
The primary target is Android offline-first survey work, with the web app used for setup, review, sync monitoring, and exports.

## Release Scope

The release supports these priority workflows:

- terrestrial vertebrates
- plants
- insects
- mainland China and Taiwan jurisdiction selection
- offline event creation, observation capture, attachment handling, reopen or restore, reconnect or sync, and export

These areas remain available but are not on the critical path for this release:

- acoustic monitoring analysis
- embeddings and SDM exploration
- broader research dashboards

## Operator Roles

### Field lead

- confirms the project, site, protocol, and jurisdiction before survey start
- verifies the Android device is prepared for offline work
- reviews sync results and export bundles after fieldwork

### Recorder

- carries the Android device
- records tracks where the protocol is route-based
- enters observations, notes, and attachments
- confirms reopen or restore works before leaving the site when possible

### Reviewer

- checks post-sync summaries and export bundles
- flags conflicts or data-quality issues
- signs off against the acceptance checklist after each survey day

## Operator Checklist

Before field deployment day:

1. Confirm the repo checkout still contains required backend model assets in `backend/checkpoints`.
2. Confirm `.env` exists, `CORS_ORIGINS` matches the real client origin, and any required API keys are present.
3. Build `.env` from `.env.field-release.template`, not from the localhost development defaults.
4. Run `sh deploy/release/deploy.sh` and wait for a healthy `http://127.0.0.1:<APP_PORT>/api/health` response.
5. Verify `docker compose ps` shows the app healthy and review `docker compose logs --tail=100 app`.
6. Run `sh deploy/release/backup.sh` once before users begin work.
7. Build the Android app with `VITE_API_BASE_URL` pointing at the real field server if the team will use native builds.

## Android Build And Install

1. In `frontend`, create `.env.local` from `.env.example`.
2. Set `VITE_API_BASE_URL` to the externally reachable field server URL.
3. Run `npm install`.
4. Run `npm run build:android`.
5. Set `ANDROID_KEYSTORE_FILE`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, and `ANDROID_KEY_PASSWORD`.
6. Run a signed release build from `frontend/android` using `.\gradlew.bat assembleRelease` on Windows or `./gradlew assembleRelease` on macOS/Linux.
7. Open `frontend/android` in Android Studio or use the Capacitor Android workflow for installation.
8. Open the app once while online after install.
9. Grant location, camera, microphone, and storage permissions before the first survey.

## Pre-Field Setup

Complete this before leaving network coverage:

1. Select or create the project.
2. Select or create the site.
3. Select the module:
   terrestrial vertebrates, plants, or insects.
4. Select the protocol.
5. Select the jurisdiction:
   mainland China or Taiwan.
6. Import the route, station, or plot asset if required by the protocol.
7. Preload offline map tiles for the working area.
8. Confirm the taxonomy package is loaded for the selected module and jurisdiction.
9. Perform a short dry run:
   save one event, one observation, and one attachment, then reopen the app and confirm the draft restores.

## In-Field Workflow

### Start a survey event

1. Open the Field Survey workspace.
2. Confirm the project, site, module, protocol, and jurisdiction.
3. Select the route or station asset if the protocol requires one.
4. Fill in observers, weather, and event fields.
5. Start track recording if the protocol is route-based.

### Record observations

For each observation:

1. Enter the species name using Chinese, English, or scientific name.
2. Confirm the taxon group and evidence type.
3. Add protocol-specific record fields.
4. Add photo or audio evidence when needed.
5. Save the observation.

### Reopen or restore check

During at least one supervised run:

1. Close the app after some observations are saved.
2. Reopen the app.
3. Confirm the active project, site, route or station, event draft, and attachments restore correctly.
4. Continue editing and save one more observation.

### Finish the event

1. Stop track recording if one is active.
2. Confirm track distance or effort looks plausible.
3. Save the event context if it has changed.
4. Leave queued work in place if there is no network.

## Sync Procedure

### If network is available

1. Pull the latest survey state when reconnecting.
2. Push queued work.
3. Confirm the sync backlog returns to zero or review any conflicts.
4. Generate the protocol export bundle for the selected jurisdiction.
5. Record the result in the controlled go-live acceptance record.

### If network is unavailable

1. Continue recording locally.
2. Do not clear app data or uninstall the app.
3. Reopen the app once if practical to confirm local restore.
4. Sync only after stable connectivity returns.

## Post-Field Review

After sync:

1. Review route or station summaries where available.
2. Review export bundle summaries for the selected protocol and jurisdiction.
3. Confirm the bundle includes manifest, event, and species outputs.
4. Save exports into the field archive for that survey day.
5. Record any mismatch between expected and actual counts, route totals, or restored state.
6. Log any blocker or major defect in `docs/controlled_go_live_issue_log.md`.

## Support Boundary

Normal survey completion must not require developer intervention.

Escalate to technical support only when:

- data is lost or cannot be restored
- sync conflict behavior cannot be understood by the operator
- export output is missing or inconsistent
- signed release APK fails to install or launch on the supported field device

## Launch Blockers

Do not advance the release stage if any of these remain unresolved:

- Android reopen or restore loses state
- plants or insects cannot complete the same offline workflow as vertebrates
- sync overwrites records silently after long offline periods
- selected route or station context is not preserved into exports
- mainland China and Taiwan exports are not distinct where required

## Staged Rollout

1. Internal dry run:
   all module and jurisdiction scenarios pass with the project team.
2. Supervised field pilot:
   real field users complete surveys with direct support available.
3. Controlled go-live:
   the release candidate has passed the acceptance checklist and the support path is ready.

## Recovery Commands

```bash
sh deploy/release/backup.sh
sh deploy/release/restore.sh --yes deploy/pilot/backups/biodiversity-field-survey-release-YYYYMMDD-HHMMSS.tar.gz
```

Restore behavior:

- validates archive contents before extraction
- creates a safety backup before replacing live data unless `SKIP_PRE_RESTORE_BACKUP=1`
- keeps the current `.env` unless the host copy is missing or `RESTORE_ENV=1`
- restores only writable field volumes, not `backend/checkpoints`
