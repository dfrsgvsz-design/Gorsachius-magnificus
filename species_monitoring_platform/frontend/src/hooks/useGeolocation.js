import { useEffect, useState } from 'react'
import {
  isNativeMobile,
  requestNativeCurrentPosition,
} from '../lib/mobileNative'

/**
 * Acquire the device's current GPS position once on mount.
 * Returns { currentPosition, setCurrentPosition }.
 *
 * `currentPosition` shape: { lat, lon, accuracy, timestamp? } | null
 *
 * When the optional `gateCheck` (typically obtained from
 * `usePermissionGate({...}).createGateCheck()`) is provided, the initial
 * GPS fetch is deferred until the user accepts the rationale modal — this
 * matches the P0 W2 "scenario-led permission UX" requirement. Without a
 * `gateCheck` the hook keeps its original behaviour and Capacitor / the
 * browser surface their own permission prompts.
 *
 * Extracted from FieldOpsTab lines 1025, 1245-1267.
 */
export default function useGeolocation({ gateCheck } = {}) {
  const [currentPosition, setCurrentPosition] = useState(null)
  const nativeMobile = isNativeMobile()

  useEffect(() => {
    let cancelled = false

    async function acquire() {
      if (typeof gateCheck === 'function') {
        const allowed = await gateCheck()
        if (cancelled || !allowed) return
      }

      if (nativeMobile) {
        try {
          const position = await requestNativeCurrentPosition()
          if (!cancelled && position) setCurrentPosition(position)
        } catch {
          // Silent: a fresh position will be requested again from the
          // foreground service or the user's manual retry.
        }
        return
      }

      if (typeof navigator === 'undefined' || !navigator.geolocation) return
      navigator.geolocation.getCurrentPosition(
        (position) => {
          if (cancelled) return
          setCurrentPosition({
            lat: position.coords.latitude,
            lon: position.coords.longitude,
            accuracy: position.coords.accuracy,
          })
        },
        () => {},
        { enableHighAccuracy: true, timeout: 7000, maximumAge: 30000 },
      )
    }

    acquire()
    return () => {
      cancelled = true
    }
  }, [gateCheck, nativeMobile])

  return { currentPosition, setCurrentPosition }
}
