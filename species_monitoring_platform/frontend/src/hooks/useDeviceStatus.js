import { useCallback, useEffect, useState } from 'react'

export default function useDeviceStatus({ pollInterval = 30000 } = {}) {
  const [status, setStatus] = useState({
    battery: null,
    storage: null,
    gps: null,
    online: typeof navigator !== 'undefined' ? navigator.onLine : true,
  })

  const refresh = useCallback(async () => {
    const next = { ...status, online: navigator.onLine }

    if ('getBattery' in navigator) {
      try {
        const battery = await navigator.getBattery()
        next.battery = {
          level: Math.round(battery.level * 100),
          charging: battery.charging,
          chargingTime: battery.chargingTime,
          dischargingTime: battery.dischargingTime,
        }
      } catch { /* not supported */ }
    }

    if ('storage' in navigator && 'estimate' in navigator.storage) {
      try {
        const estimate = await navigator.storage.estimate()
        next.storage = {
          usage: estimate.usage || 0,
          quota: estimate.quota || 0,
          usagePercent: estimate.quota ? Math.round((estimate.usage / estimate.quota) * 100) : null,
          usageMB: Math.round((estimate.usage || 0) / (1024 * 1024)),
          quotaMB: Math.round((estimate.quota || 0) / (1024 * 1024)),
        }
      } catch { /* not supported */ }
    }

    if ('geolocation' in navigator) {
      next.gps = { available: true }
    }

    setStatus(next)
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, pollInterval)
    return () => clearInterval(id)
  }, [refresh, pollInterval])

  useEffect(() => {
    const onOnline = () => setStatus((s) => ({ ...s, online: true }))
    const onOffline = () => setStatus((s) => ({ ...s, online: false }))
    window.addEventListener('online', onOnline)
    window.addEventListener('offline', onOffline)
    return () => {
      window.removeEventListener('online', onOnline)
      window.removeEventListener('offline', onOffline)
    }
  }, [])

  const warnings = []
  if (status.battery && status.battery.level < 20 && !status.battery.charging) {
    warnings.push({ type: 'battery', level: 'warning', message: `Battery low: ${status.battery.level}%` })
  }
  if (status.battery && status.battery.level < 10 && !status.battery.charging) {
    warnings.push({ type: 'battery', level: 'critical', message: `Battery critical: ${status.battery.level}%` })
  }
  if (status.storage && status.storage.usagePercent > 90) {
    warnings.push({ type: 'storage', level: 'warning', message: `Storage almost full: ${status.storage.usagePercent}%` })
  }
  if (!status.online) {
    warnings.push({ type: 'network', level: 'info', message: 'Device is offline' })
  }

  return { ...status, warnings, refresh }
}
