# Legacy Test Artefacts

Pre-2026-06 ad-hoc playwright/test scripts and log files. Consolidated here
on 2026-06-10 (ticket #C, Batch 2) so the repo root and
`species_monitoring_platform/frontend/` stop looking like a manual QA dump.

**Do not extend this directory.** Add new tests under
[`../specs/`](../specs/). This folder is read-only history.

## File inventory + original locations

| File | Origin | Purpose (best guess) |
|---|---|---|
| `playwright_recon_log.txt` | repo root | Output of an early reconnaissance run that printed visible buttons/links on the species dashboard (Chinese-localized). Useful as a snapshot of pre-2026-06 sidebar copy. |
| `playwright_fieldops_native_pass_log.txt` | repo root | Field Ops tab pass log capturing the "华南地区外业项目" default-project behaviour and section labels (项目 / 样点 etc.). Referenced by `02-survey-protocol.spec.ts` for selector inspiration. |
| `playwright_fieldops_audio_pass_log.txt` | repo root | Same shape, audio-capture variant. |
| `playwright_fieldops_after_fix_log.txt` | repo root | Field Ops re-run after some fix (unspecified). |
| `playwright_fieldops_detail_log.txt` | repo root | Field Ops detail-view tab log. |
| `playwright_transect_report_body.txt` | repo root | Transect report rendering output. |
| `test-ui.mjs` | `species_monitoring_platform/frontend/` | Sidebar smoke: opens dashboard → clicks each nav button → screenshots. Was wired into species/frontend `package.json` `lint` until 2026-06-10. Equivalent functionality now in `specs/01-app-boot.spec.ts` (more focused). |
| `test-local-store.mjs` | `species_monitoring_platform/frontend/` | IndexedDB local-store smoke (read/write). Equivalent partially in `specs/04-offline-submit.spec.ts`; deeper assertions are still TODO. |
| `test-local-store-log.txt` | `species_monitoring_platform/frontend/` | Its own pass log. |
| `test-local-store-offline-log.txt` | `species_monitoring_platform/frontend/` | Offline-path pass log. |
| `test-webview-cdp.mjs` | `species_monitoring_platform/frontend/` | Chrome DevTools Protocol bridge test (debugging Capacitor WebView). Niche / out of scope for the 5-step gate. |
| `test-webview-hybrid-local.mjs` | `species_monitoring_platform/` | Hybrid-local-mode WebView regression. |
| `test-apk-deep.mjs` | `species_monitoring_platform/frontend/` | APK-deep behavioural test (post-build). Out of scope for browser E2E. |
| `test-apk-deep-v2.mjs` | `species_monitoring_platform/frontend/` | v2 of the above. |
| `test-apk-equivalent.mjs` | `species_monitoring_platform/frontend/` | Equivalence test (web vs APK behaviour). |
| `test-offline-output.txt` | `species_monitoring_platform/frontend/` | Manual offline-test run output. |
| `test-run-output.txt` | `species_monitoring_platform/frontend/` | Manual general-test run output. |

## What carried forward into `../specs/`

- `01-app-boot.spec.ts` ⟵ inspired by `test-ui.mjs`'s sidebar smoke pattern.
- `02-survey-protocol.spec.ts` ⟵ used field-ops native pass log to confirm
  default project naming.
- `03-checkin.spec.ts` ⟵ new (no good legacy equivalent).
- `04-offline-submit.spec.ts` ⟵ adapted from `test-local-store.mjs` +
  `test-local-store-offline-log.txt`.
- `05-reconnect-sync.spec.ts` ⟵ new (no good legacy equivalent — the
  reconnect path was only manually verified).

## What was NOT carried forward (intentionally out of E2E scope)

- `test-webview-cdp.mjs`, `test-webview-hybrid-local.mjs` — these are
  debugging tools for the Capacitor WebView bridge, not regression tests.
  Belong with the Android packaging concern (`submission/06_packaging_signing_runbook.md`),
  not browser E2E.
- `test-apk-*.mjs` — APK-deep tests target installed-on-device behaviour
  via ADB. The browser-based E2E suite cannot replace these; they should be
  re-homed under a separate `tests/android-instrumented/` directory the next
  time someone owns Android device CI (see Batch 4 / future).

## If you actually need to run one of these legacy scripts

They still work (mostly). From the repo root:

```powershell
cd species_monitoring_platform/frontend
node ../../tests/e2e/_legacy/test-ui.mjs
```

But understand they require a running dev server on `http://127.0.0.1:4000`
and they are not gated, not reported, and will not surface failures
anywhere. If you find yourself relying on one regularly, that is the signal
to port it into `../specs/`.
