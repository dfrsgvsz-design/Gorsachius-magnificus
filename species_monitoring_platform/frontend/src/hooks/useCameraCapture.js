import { useCallback, useState } from 'react'
import {
  CameraSource,
  capturePhotoAttachment,
  ImpactStyle,
  isNativeMobile,
  pulseFeedback,
} from '../lib/mobileNative'
import { getApiErrorMessage } from '../lib/api'

/**
 * Pure orchestration for a single photo-capture attempt. Exported so it can
 * be unit-tested without spinning up a React renderer.
 *
 * Drives the supplied callbacks in the order the hook expects:
 *   1. `onSerializing(true)` before invoking `captureFn`
 *   2. `onError(null)` to clear any previous error
 *   3. `captureFn(source)` is awaited
 *   4. On success and a non-null attachment, `onAttachment(attachment)` fires
 *   5. On thrown error, `onError(message)` fires with a localized fallback
 *   6. `onSerializing(false)` always runs in `finally`
 *
 * @returns {{ ok: boolean, attachment?: object, error?: string }}
 */
export async function capturePhotoWithState({
  captureFn,
  source,
  callbacks,
  fallbackMessage = 'Unable to capture a field photo on this device.',
}) {
  const { onSerializing, onError, onAttachment } = callbacks || {}
  onSerializing?.(true)
  onError?.(null)
  try {
    const attachment = await captureFn(source)
    if (!attachment) {
      return { ok: true, attachment: null }
    }
    onAttachment?.(attachment)
    return { ok: true, attachment }
  } catch (err) {
    const message = getApiErrorMessage(err, fallbackMessage)
    onError?.(message)
    return { ok: false, error: message }
  } finally {
    onSerializing?.(false)
  }
}

/**
 * React hook wrapping the native camera workflow. Returns
 * `{ cameraStatus, serializingCamera, capturePhoto }`.
 *
 * `capturePhoto(source?)` resolves to the same shape as
 * `capturePhotoWithState` so callers can chain UI side effects (e.g. open an
 * observation sheet) only on success.
 *
 * Pass `captureFn` to override the underlying native call in tests; the
 * default delegates to `mobileNative.capturePhotoAttachment`.
 *
 * Pass `requireNative=false` to also allow the hook on browser-only builds
 * (the default mirrors `FieldOpsTab` which only exposes the camera button on
 * Capacitor builds).
 */
export default function useCameraCapture({
  onAttachment,
  onError,
  captureFn = capturePhotoAttachment,
  requireNative = true,
  fallbackMessage,
  // Optional `async () => boolean` returned by `usePermissionGate
  // ({...}).createGateCheck()`. When provided, `capturePhoto` awaits it
  // before invoking the native API so the rationale modal can render
  // first. When omitted, the hook keeps its original behaviour and
  // delegates permission handling to mobileNative.capturePhotoAttachment.
  gateCheck,
} = {}) {
  const [cameraStatus, setCameraStatus] = useState('idle')
  const [serializingCamera, setSerializingCamera] = useState(false)

  const capturePhoto = useCallback(
    async (source = CameraSource.Camera) => {
      if (requireNative && !isNativeMobile()) {
        return { ok: false, error: 'Camera capture is only available in the native app.' }
      }
      if (typeof gateCheck === 'function') {
        const allowed = await gateCheck()
        if (!allowed) {
          const message = 'Camera permission was not granted.'
          onError?.(message)
          setCameraStatus('error')
          return { ok: false, error: message, blockedByGate: true }
        }
      }
      setCameraStatus('capturing')
      const result = await capturePhotoWithState({
        captureFn,
        source,
        callbacks: {
          onSerializing: setSerializingCamera,
          onError,
          onAttachment,
        },
        fallbackMessage,
      })
      if (result.ok && result.attachment) {
        try {
          await pulseFeedback(ImpactStyle.Light)
        } catch {
          // Haptic failures are cosmetic; never block the capture flow.
        }
      }
      setCameraStatus(result.ok ? 'idle' : 'error')
      return result
    },
    [captureFn, fallbackMessage, gateCheck, onAttachment, onError, requireNative],
  )

  return {
    cameraStatus,
    serializingCamera,
    capturePhoto,
  }
}
