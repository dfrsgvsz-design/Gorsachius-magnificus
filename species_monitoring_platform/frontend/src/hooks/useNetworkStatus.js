import { useEffect, useState } from 'react'

/**
 * Track browser online/offline status.
 * Returns { isOnline: boolean }.
 *
 * Extracted from FieldOpsTab lines 1026, 1269-1279.
 */
export default function useNetworkStatus() {
  const [isOnline, setIsOnline] = useState(
    typeof navigator === 'undefined' ? true : navigator.onLine,
  )

  useEffect(() => {
    if (typeof window === 'undefined') return undefined
    const handleOnline = () => setIsOnline(true)
    const handleOffline = () => setIsOnline(false)
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])

  return { isOnline }
}
