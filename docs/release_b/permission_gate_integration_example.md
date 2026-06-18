# Permission gate integration example (Batch 7)

After Batch 4 introduced the `usePermissionGate` hook + scenario-led modal,
and Batch 7 wired the three capture hooks (`useCameraCapture`,
`useAudioCapture`, `useGeolocation`) to accept an optional `gateCheck`, the
following pattern threads everything together so the 8 acceptance scenarios
(`4 sensitive permissions × {accept, deny}`) actually run end-to-end.

Backwards compatible: omitting `gateCheck` is a no-op — every hook keeps
its pre-Batch 7 behaviour and lets Capacitor / the browser surface its
own permission prompt.

## Recipe: wire one permission

```jsx
import {
  Camera,
  CameraSource,
} from '@capacitor/camera'
import { useTranslation } from 'react-i18next'

import useCameraCapture from '../hooks/useCameraCapture'
import usePermissionGate from '../hooks/usePermissionGate'
import PermissionRationaleModal from '../components/permissions/PermissionRationaleModal'
import PermissionDeniedFallback from '../components/permissions/PermissionDeniedFallback'

function PhotoButton({ onAttachment, onError }) {
  const { i18n } = useTranslation()
  const locale = i18n.language.startsWith('zh') ? 'zh' : 'en'

  // 1. Create the gate per permission. `check` and `request` are platform
  //    adapters — different shapes per Capacitor plugin.
  const gate = usePermissionGate({
    permissionId: 'camera',
    check: async () => (await Camera.checkPermissions()).camera,
    request: async () => (await Camera.requestPermissions({ permissions: ['camera'] })).camera,
  })

  // 2. Hand the gate's check to the capture hook. `capturePhoto` will now
  //    await the modal before invoking the OS prompt.
  const { capturePhoto, cameraStatus } = useCameraCapture({
    onAttachment,
    onError,
    gateCheck: gate.createGateCheck(),
  })

  return (
    <>
      <button onClick={() => capturePhoto(CameraSource.Camera)}>
        Take photo
      </button>

      {/* 3. Modal renders only when the gate flips status to 'prompting'.
            Its Accept / Skip wire to the gate, which settles the pending
            promise inside `capturePhoto`. */}
      <PermissionRationaleModal
        open={gate.status === 'prompting'}
        permissionId="camera"
        locale={locale}
        onAccept={gate.accept}
        onSkip={gate.skip}
      />

      {/* 4. When the user denies, the gate goes to 'denied' (or 'blocked'
            on "Don't ask again"). Replace the capture button with the
            scenario-aware fallback that explains what they can still do. */}
      {(gate.status === 'denied' || gate.status === 'blocked') && (
        <PermissionDeniedFallback
          permissionId="camera"
          locale={locale}
          blocked={gate.status === 'blocked'}
          onRetry={gate.reset}
          onOpenSettings={() => Camera.requestPermissions({ permissions: ['camera'] })}
        />
      )}
    </>
  )
}
```

## Why a `gateCheck` returns a Promise<boolean>

The capture hooks (`useCameraCapture`, `useAudioCapture`, `useGeolocation`)
have ONE moment where the rationale matters: just before they hit the
native API. The cleanest contract is:

> "Before I call the OS, let me `await` an async predicate. If it resolves
> `true`, I proceed. If `false`, I bail with a stable error shape."

`usePermissionGate(...).createGateCheck()` returns exactly that. It hides
the React-state + modal lifecycle inside the gate, so the capture hook
stays unaware of how the UI is rendered.

## Mapping to the 8 acceptance scenarios

| # | Permission           | User action | Expected UI                                  |
|---|----------------------|-------------|----------------------------------------------|
| 1 | location             | Accept      | Map shows blue dot, observation auto-snap on |
| 2 | location             | Deny        | Manual coordinate entry, recover hint        |
| 3 | camera               | Accept      | Native camera launches                       |
| 4 | camera               | Deny        | "Upload from gallery" fallback               |
| 5 | microphone           | Accept      | Recording starts                             |
| 6 | microphone           | Deny        | Text-note fallback                           |
| 7 | backgroundLocation   | Accept      | FGS notification, full track captured        |
| 8 | backgroundLocation   | Deny        | "Foreground-only track" mode label           |

All eight live in `src/lib/permissionCopy.js` (Batch 4). The Playwright
e2e suite can drive each by stubbing the gate's `check` / `request`
adapters.

## What this batch does NOT do (out of scope)

- **Does not wire `FieldOpsTab`**. The existing call sites keep using the
  un-gated path (Capacitor surfaces its own dialogs). A follow-up batch
  will replace them with the gated pattern above, one permission at a
  time, with e2e coverage for each scenario.
- **Does not handle `backgroundLocation`** in `useGeolocation`. The
  current hook only requests foreground GPS; the background variant
  lives in `@capacitor-community/background-geolocation` and gets its
  own gate when the BackgroundGeolocation watcher lands (tied to Batch 5
  scaffolding).
- **Does not auto-retry capture after Accept**. The consumer pattern
  above re-clicks the button; auto-retry is doable but adds complexity
  that is not yet justified by the field workflow.

## Verification recipes

### Unit (vitest, runs in CI)
- `useCameraCapture.test.js > capturePhotoWithState + gateCheck composition`
  verifies the native API is never called when the gate rejects.
- `usePermissionGate.test.js > gate-check resolver contract` verifies
  the promise resolves with the right boolean for each user action
  (Accept / Skip / cancel-on-re-entry).

### Manual (Capacitor build on Android)
1. Build a release APK, install on a fresh device.
2. Open Field Ops → tap photo button:
   - Expect: rationale modal shows BEFORE Android's OS dialog.
   - Tap Skip: expect `PermissionDeniedFallback` in place of the camera.
   - Tap Accept → Allow in OS dialog: expect camera launches.
3. Reset permissions in Android settings → repeat with Deny: expect
   `PermissionDeniedFallback` AGAIN (gate state recovers on hook mount).
4. Reset with "Don't ask again": gate should land in `'blocked'`, the
   fallback shows the "Open Settings" CTA prominently.

### E2E (Playwright)
A future spec can stub the gate via:
```js
await page.exposeFunction('__stubCameraGate', () => true)
// then evaluate window.__stubCameraGate from inside a test fixture
```
This will land alongside the FieldOpsTab wiring follow-up.
