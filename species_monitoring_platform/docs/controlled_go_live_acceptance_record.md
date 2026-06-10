# Controlled Go-Live Acceptance Record

Fill one copy of this record for each release candidate.

## Release Metadata

- Release version:
- APK filename:
- APK SHA256:
- Release date:
- Reviewer:
- Field lead:
- Backend commit or package reference:
- Android build workstation:

## Environment Snapshot

- `.env` prepared from `.env.field-release.template`: yes or no
- `CORS_ORIGINS` verified against real client origin: yes or no
- `VITE_API_BASE_URL` verified against real field server: yes or no
- Backup baseline created before validation: yes or no
- VPN / firewall / allowlist access validated: yes or no

## Automated Gates

- `python -m unittest discover backend/tests -v`
- `npm run test -- --run`
- `npm run build`
- `npm run build:android`
- `docker compose up -d --build`
- `/api/health` returns healthy

Record pass/fail, operator, and evidence link for each item.

## Android RC Verification

- Signed release APK installs successfully.
- First launch while online succeeds.
- Permissions granted successfully.
- Project and site selection persist.
- Offline event creation works.
- Offline observation and attachment capture works.
- Force close and reopen restores draft state.
- Reconnect and sync succeed.
- Export succeeds after sync.

For each item, record:

- Pass or fail
- Device model
- Android version
- Tester
- Notes or defect ID

## Module And Jurisdiction Matrix

Complete one row per scenario.

| Module | Jurisdiction | Protocol | Offline Create | Reopen Restore | Sync | Export | Totals Correct | Tester | Result | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| terrestrial_vertebrates | mainland_china |  |  |  |  |  |  |  |  |  |
| terrestrial_vertebrates | taiwan |  |  |  |  |  |  |  |  |  |
| plants | mainland_china |  |  |  |  |  |  |  |  |  |
| plants | taiwan |  |  |  |  |  |  |  |  |  |
| insects | mainland_china |  |  |  |  |  |  |  |  |  |
| insects | taiwan |  |  |  |  |  |  |  |  |  |

## Route, Track, And Conflict Checks

- Route import verified:
- Track logging verified:
- Snapped and direct observations remain consistent:
- Duplicate push handled idempotently:
- Stale base timestamp conflict visible:
- Long offline queue handled:
- Mixed attachment payloads retained:

Record evidence and defect IDs where applicable.

## Release Decision

- Ready for internal dry run: yes or no
- Ready for supervised field pilot: yes or no
- Ready for controlled go-live: yes or no

Blocking defects:

- 

Approvers:

- Product or field lead:
- Technical owner:
- Release operator:
