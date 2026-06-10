# Biodiversity Field Release Acceptance Checklist

## Objective

The release is acceptable when one field user can complete offline biodiversity survey work on Android across terrestrial vertebrates, plants, and insects without developer intervention and without losing data.

Record each release-candidate run in `docs/controlled_go_live_acceptance_record.md`.

## Core Acceptance Matrix

Pass all scenarios below before go-live:

1. Terrestrial vertebrates:
   Create or select a project and site, complete one route-based or station-based protocol, save observations, sync, and export a jurisdiction bundle.
2. Plants:
   Complete one plant quadrat or plant transect scenario, reopen the app during the workflow, continue editing, sync, and export.
3. Insects:
   Complete one insect transect scenario with offline route context, restore after reopen, sync, and export.

## Jurisdiction Coverage

Run at least one mainland China and one Taiwan scenario for each prioritized module:

- `terrestrial_vertebrates`
- `plants`
- `insects`

Each scenario must confirm:

- protocol selection is correct
- taxonomy package selection is correct
- jurisdiction-specific naming and status behavior are preserved
- export files use the intended jurisdiction scope

## Offline Android Checks

- Create a survey event while offline.
- Save observations and attachments while offline.
- Close and reopen the app during an active session.
- Restore the active project, site, route or station, event context, and queued observations.
- Continue editing after reopen.
- Reconnect and sync successfully without manual repair.

## Route, Track, And Asset Checks

- Import a route file for each prioritized route-based protocol.
- Start and stop track recording on Android.
- Keep snapped observations, direct observations, and walked tracks consistent.
- Confirm route or station summaries do not double count records.
- Export JSON or CSV route-report outputs where route summaries are supported.

## Export Bundle Checks

For each prioritized module and jurisdiction pair:

- Generate an export bundle successfully.
- Confirm the bundle includes a manifest plus CSV outputs for event and species data.
- Confirm route or station summary outputs are present when applicable.
- Confirm species-list rows match saved observations.

## Sync And Conflict Checks

- Duplicate push is idempotent.
- Stale base timestamp creates a visible conflict instead of silent overwrite.
- Long offline queues still push successfully after reconnect.
- Mixed attachment payloads remain attached after sync.

## Regression Checks

- Backend unit and smoke tests pass.
- Frontend tests pass.
- Android signed release APK builds successfully.
- Existing vertebrate export behavior still works.
- New plants and insects export coverage passes.

## Staged Release Decision

### Ready for internal dry run

- All module and jurisdiction scenarios pass locally.
- Operators can complete offline Android workflows without developer help.
- Export bundles are present for vertebrates, plants, and insects.

### Ready for supervised field pilot

- Internal dry run issues are resolved.
- Reopen/restore behavior is trusted on Android.
- Sync conflicts are understandable to operators.
- Route and export totals stay consistent after reconnect.

### Ready for controlled go-live

- Supervised field pilot completes without blocker defects.
- Runbook steps match real operator behavior.
- Android build, backend tests, and export checks all pass on the release candidate.
- Release metadata, APK checksum, `.env` snapshot, and baseline backup are stored with the release record.

## Not Ready

Do not go live if any of these remain unresolved:

- offline state cannot be trusted after app close and reopen
- plants or insects cannot complete end-to-end export
- mainland China and Taiwan behavior are flattened incorrectly
- route summaries or bundle totals are inconsistent
- field operators still need developer intervention for normal survey completion
