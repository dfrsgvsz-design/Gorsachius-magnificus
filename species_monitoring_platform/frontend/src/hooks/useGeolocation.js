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
 * Extracted from FieldOpsTab lines 1025, 1245-1267.
 */
export default function useGeolocation() {
  const [currentPosition, setCurrentPosition] = useState(null)
  const nativeMobile = isNativeMobile()

  useEffect(() => {
    if (nativeMobile) {
      requestNativeCurrentPosition()
        .then((position) => {
          if (position) setCurrentPosition(position)
        })
        .catch(() => {})
      return
    }

    if (typeof navigator === 'undefined' || !navigator.geolocation) return
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setCurrentPosition({
          lat: position.coords.latitude,
          lon: position.coords.longitude,
          accuracy: position.coords.accuracy,
        })
      },
      () => {},
      { enableHighAccuracy: true, timeout: 7000, maximumAge: 30000 },
    )
  }, [nativeMobile])

  return { currentPosition, setCurrentPosition }
}
