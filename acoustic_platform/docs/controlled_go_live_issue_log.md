# Controlled Go-Live Issue Log

Use this log during release-candidate validation, supervised pilot, and the first observation cycle after controlled go-live.

| ID | Date | Stage | Module | Jurisdiction | Environment | Severity | Summary | Reproduction | Workaround | Owner | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| RC-001 |  | internal_dry_run |  |  | android / server / sync / export |  |  |  |  |  | open |

## Severity Guide

- `blocker`: prevents survey completion, restore, sync, or export
- `major`: workflow completes only with operator confusion or risky workaround
- `minor`: workflow completes but quality, wording, or ergonomics need correction

## Escalate Immediately

- data loss or irrecoverable draft loss
- sync overwrite without visible conflict
- export totals inconsistent with saved observations
- route or station context missing from final outputs
- Android release APK cannot install or launch on supported field devices
