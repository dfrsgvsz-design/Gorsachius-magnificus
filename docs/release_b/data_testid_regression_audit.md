# data-testid regression audit — Batch 1–5

**Date**: 2026-06-10
**Audited commits**: `05ec32a..e37dcfa` (initial import → release prep)
**Coverage**: 18 unique testids in `species_monitoring_platform/frontend`
**Acoustic parity**: 0 testids (gap documented in section 4)

## Method

1. Enumerated every `data-testid="..."` literal in the species SPA source.
2. Cross-referenced each testid's owning DOM node against the file-level diffs
   in commits `f7f63af`, `2e0d5d0`, `6624c09`, `f42f416`, `9e68384`.
3. Looked up every consumer in `tests/e2e/specs/01..05` to confirm none break.
4. Filed a parity gap for the acoustic SPA, which today has zero testids.

No Playwright run was required for this audit because the changed DOM
surfaces and the testid surfaces are disjoint (see section 2).

---

## 1. Species testid inventory (18 unique)

Templates like `project-row-{id}` are counted as one testid.

| # | testid | Owning file | Used by spec(s) |
|---|---|---|---|
| 1 | `nav-tab-{tabId}` | `src/App.jsx:338` | 01, 02, 03, 04, 05 |
| 2 | `app-status-dot` | `src/App.jsx:368` | 01 |
| 3 | `step-tab-{tabId}` | `src/components/tabs/FieldOpsTab.jsx:1545` | 02 |
| 4 | `network-chip` | `src/components/tabs/FieldOpsTab.jsx:1556` | 04, 05 |
| 5 | `sync-pull` | `src/components/tabs/FieldOpsTab.jsx:1565` | (none yet) |
| 6 | `sync-push` | `src/components/tabs/FieldOpsTab.jsx:1573` | 05 |
| 7 | `setup-level-header` | `src/components/tabs/FieldOpsTab.jsx:1604` | 02 |
| 8 | `project-row-{project_id}` | `src/components/tabs/FieldOpsTab.jsx:1642` | 02, 03, 04, 05 |
| 9 | `site-row-{site_id}` | `src/components/tabs/FieldOpsTab.jsx:1695` | (none yet) |
| 10 | `route-row-{route_id}` | `src/components/tabs/FieldOpsTab.jsx:1746` | (none yet) |
| 11 | `prep-observer` | `src/components/tabs/FieldOpsTab.jsx:1802` | 02, 03, 04, 05 |
| 12 | `prep-weather` | `src/components/tabs/FieldOpsTab.jsx:1814` | 03 |
| 13 | `prep-start` | `src/components/tabs/FieldOpsTab.jsx:1842` | 03, 04, 05 |
| 14 | `survey-end` | `src/components/tabs/FieldOpsTab.jsx:1903` | 03 |
| 15 | `obs-fab` | `src/components/tabs/FieldOpsTab.jsx:1999` | 03, 04, 05 |
| 16 | `sync-pending-count` | `src/components/fieldops/SyncPanel.jsx:16` | (none yet) |
| 17 | `obs-species-input` | `src/components/fieldops/ComboField.jsx:244` | 03, 04, 05 |
| 18 | `obs-submit` | `src/components/fieldops/ObservationFormPanel.jsx:188` | 03, 04, 05 |

---

## 2. Cross-reference: what my Batches changed vs which testids live there

| Batch | File touched | Testids in that file | Affected? | Notes |
|---|---|---|---|---|
| 1 | `src/lib/surveyOffline.js` | 0 | no | export-only change |
| 1 | `src/hooks/useTrackRecording.js` | 0 | no | hook, no DOM |
| 2 | `src/components/fieldops/FieldSurveyMap.jsx` | 0 | no | leaf map component, no testids |
| 2 | `src/components/common/FullScreenMap.jsx` | 0 | no | not rendered inside FieldOps tab |
| 2 | `src/components/fieldops/EssentialWorkflowPanel.jsx` | 0 | no | unused alt panel; no consumers |
| 2 | `src/components/tabs/FieldOpsTab.jsx` | 13 | **no** | only added `userPosition={currentPosition}` to `<FieldSurveyMap>` (lines 1968-1978); the 13 testids in this file live on the nav/setup/survey/observation chrome, not on the map block |
| 3 | `src/hooks/useCameraCapture.js` (new) | 0 | no | new file, no DOM |
| 3 | `src/hooks/useAudioCapture.js` | 0 | no | hook, no DOM |
| 3 | `src/components/tabs/FieldOpsTab.jsx` | 13 | **no** | replaced inline `handleStartAudioCapture` / `handleStopAudioCapture` / `handleCapturePhoto` with hook-backed counterparts; same names exported, same consumer props (`onStartAudioCapture`, `onStopAudioCapture`, `onCapturePhoto`) — ObservationFormPanel's `obs-submit` testid is unaffected |
| 4 | `src/lib/permissionCopy.js` (new) | 0 | no | data only |
| 4 | `src/hooks/usePermissionGate.js` (new) | 0 | no | hook, no DOM |
| 4 | `src/components/permissions/*` (new) | 0 | no | new components, no testids yet |
| 5 | `android/app/src/main/AndroidManifest.xml` | 0 | no | Android config |
| 5 | `capacitor.config.json` | 0 | no | Capacitor config |

**Result**: zero overlap between changed DOM nodes and the 18 testids. All
five `tests/e2e/specs/*.spec.ts` files will continue to resolve every
selector they currently use.

## 3. Recommended follow-up testids for species (gap analysis)

These would tighten coverage of the surfaces my Batches added or rewrote:

| Surface | Suggested testid | Anchor | Why |
|---|---|---|---|
| Batch 2 map | `field-map` | `<MapContainer>` outer `div` | Lets specs assert the map mounted without coupling to leaflet's internal classes |
| Batch 2 user position | `user-position-marker` | `<CircleMarker>` for the blue dot | Verify position rendering across geolocation fixtures |
| Batch 2 cluster wrapper | `marker-cluster-group` | `<MarkerClusterGroup>` | Distinguish clustering bug from missing data |
| Batch 4 modal | `permission-rationale` | outermost `<div role="dialog">` | E2E for permission UX scenarios |
| Batch 4 modal action | `permission-accept` / `permission-skip` | the two buttons | Drive the 8 acceptance scenarios |
| Batch 4 fallback | `permission-denied-fallback` | the `<section role="status">` | Assert degraded mode shows up |

Not added in this batch (out of scope of Item 3). File a separate ticket if
the team wants these wired in before Item 8 (sync engine E2E hardening).

---

## 4. Acoustic parity gap (0 → ?)

`acoustic_platform/frontend/src/` has **zero** `data-testid` attributes
today. The cross-app `tests/e2e/playwright.config.ts` already defines an
`ACOUSTIC_BASE_URL` for `http://127.0.0.1:8001` and is wired to accept an
`acoustic-*` project, but no specs exist yet because there are no stable
selectors.

### Recommended minimum testid set for acoustic (parity with species)

Add these eight to give Item 8-style E2E coverage on the acoustic side:

| Surface | Suggested testid | Owning file (today) |
|---|---|---|
| Top nav | `nav-tab-{tabId}` | `acoustic_platform/frontend/src/App.jsx` |
| Health pill | `app-status-dot` | `acoustic_platform/frontend/src/App.jsx` |
| Monitor tab → start listen | `monitor-start` | `components/tabs/MonitorTab.jsx` |
| Monitor tab → stop listen | `monitor-stop` | `components/tabs/MonitorTab.jsx` |
| Verify tab → table row | `verify-row-{detection_id}` | `components/tabs/VerifyTab.jsx` |
| Verify tab → confirm | `verify-confirm` | same |
| Verify tab → reject | `verify-reject` | same |
| Soundscape tab → date picker | `soundscape-date` | `components/tabs/SoundscapeTab.jsx` |

### Suggested rollout

1. **Phase 1** (5 min, this batch): file the recommended list above as a
   tracked task in `submission/governance/` so it doesn't get lost.
2. **Phase 2** (next batch): add the 8 testids to acoustic SPA source. No
   visual change, no behavior change — pure attribute additions.
3. **Phase 3** (post-Item 8): mirror specs 01 / 03 / 05 into
   `tests/e2e/specs/acoustic/*.spec.ts` and add an `acoustic-chromium`
   project to the playwright config.

This sequencing avoids enabling E2E selectors before the underlying surfaces
are themselves stable, which has bitten this repo before (see legacy
`tests/e2e/_legacy/` artifacts).

---

## 5. Conclusion

- **0 regressions** introduced by Batches 1–5 across the 18 species testids.
- **0 spec files** need updating in `tests/e2e/specs/`.
- **Acoustic gap is documented** but not closed in this batch.
- **6 follow-up testids** suggested for the new Batch 2/4 surfaces.
