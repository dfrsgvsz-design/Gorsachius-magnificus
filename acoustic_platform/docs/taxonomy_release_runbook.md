# Taxonomy Release Runbook

## Purpose

This runbook describes the controlled taxonomy release process for the biodiversity field survey platform.
Runtime survey lookup must use the current local taxonomy release only.

## Release Inputs

- Place repo-controlled source manifests under `backend/data/taxonomy_sources/<release_id>/...`
- Place normalized release assets under `backend/data/taxonomy_releases/<release_id>/...`
- Validate and promote the full manifest with:
  - `python scripts/promote_taxonomy_full_release.py --release-id <release_id> --check-only`
  - `python scripts/promote_taxonomy_full_release.py --release-id <release_id>`
- The promotion script writes:
  - `backend/data/taxonomy_packages.json`
  - `backend/data/taxonomy_releases/<release_id>/release_manifest.json`

## Full Release Asset Rules

- Keep dual-layer assets in the repo:
  - `taxonomy_sources/<release_id>/...` for raw source snapshots and audit manifests
  - `taxonomy_releases/<release_id>/...` for normalized release entries consumed by rebuild/import
- Every `source_manifest.json` must include:
  - `release_id`
  - `jurisdiction`
  - `program`
  - `submodule_counts`
  - `official_expected_count`
  - `source_files`
  - `source_version_date`
  - `license_note`
  - `mapping_notes`
- `source_manifest.source_files` must resolve under `backend/data/taxonomy_releases/<release_id>/...`
- Mainland terrestrial vertebrates must declare `birds=1505`
- Full release packages must not include `local_seed_assets`

## Build And Validate

1. Run `python scripts/promote_taxonomy_full_release.py --release-id <release_id> --check-only`.
2. Run `python scripts/promote_taxonomy_full_release.py --release-id <release_id>`.
3. Run `POST /api/admin/taxonomy/releases/rebuild?force=true&activate=false`.
4. Review `GET /api/admin/taxonomy/discrepancy-report?release_id=<release_id>`.
5. Confirm `GET /api/admin/taxonomy/releases/current` still points at the previous known-good release.
6. Confirm `GET /api/health` exposes taxonomy blockers for the candidate when discrepancy, parity, or review items remain.
7. Do not activate if any of these remain:
   - `count_parity_ok=false`
   - open match reviews
   - non-exhaustive package content for the intended release candidate

## Activate

1. Record the previous current release id.
2. Activate the candidate with `POST /api/admin/taxonomy/releases/<release_id>/activate`.
3. Verify `/api/health` reports:
   - `current_taxonomy_release_id`
   - `taxonomy_exhaustive_package_count`
   - `taxonomy_count_parity_ok`
   - `taxonomy_review_backlog_count`

## Android Offline Verification

1. Pull survey metadata on Android while online.
2. Verify the selected taxonomy package stores:
   - `taxonomy_release_id`
   - `checksum`
   - `count_parity_ok`
   - `review_status`
   - `is_current_release`
3. Close and reopen the app and confirm the same package metadata restores.
4. Complete one search -> event -> observation -> sync -> export scenario.
5. Switch the server to another release and verify checksum mismatch is detected before export.

## Rollback

1. Re-activate the previous known-good release id.
2. Verify search and export resolve against the previous release.
3. Re-activate the candidate only after rollback validation succeeds.

## Go-Live Gate

Do not mark controlled go-live ready if:

- any package remains seed-only for the intended full release
- any package count mismatches its source manifest
- taxonomy review backlog is non-zero
- Android offline taxonomy package checksum does not match the server package checksum
