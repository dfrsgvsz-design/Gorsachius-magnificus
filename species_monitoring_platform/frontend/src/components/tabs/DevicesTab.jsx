import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { useTranslation } from 'react-i18next'
import {
  Cpu,
  Loader2,
  MapPin,
  Radio,
  RefreshCw,
  Wifi,
  WifiOff,
  X,
} from 'lucide-react'
import {
  getApiErrorMessage,
  getDeviceMap,
  getDevices,
  registerDevice,
  removeDevice,
} from '../../lib/api'
import {
  EmptyPanel,
  InfoNote,
  LoadingState,
  PageHero,
  SectionHeader,
  StatCard,
  StatusBanner,
} from '../common'

function hasCoordinate(device) {
  const lat = Number(device?.latitude)
  const lon = Number(device?.longitude)
  return Number.isFinite(lat) && Number.isFinite(lon)
}

function buildDeviceTypeOptions(t) {
  return [
    ['generic', t('devicesPage.deviceTypes.generic')],
    ['raspberry_pi', t('devicesPage.deviceTypes.raspberry_pi')],
    ['audiomoth', t('devicesPage.deviceTypes.audiomoth')],
    ['song_meter', t('devicesPage.deviceTypes.song_meter')],
    ['mobile', t('devicesPage.deviceTypes.mobile')],
  ]
}

export default function DevicesTab() {
  const { t } = useTranslation()
  const [devices, setDevices] = useState([])
  const [mapData, setMapData] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [refreshing, setRefreshing] = useState(false)
  const [savingDevice, setSavingDevice] = useState(false)
  const [removingId, setRemovingId] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [mobilePanel, setMobilePanel] = useState('list')
  const [form, setForm] = useState({
    device_id: '',
    name: '',
    latitude: '',
    longitude: '',
    type: 'generic',
  })

  const deviceTypeOptions = useMemo(() => buildDeviceTypeOptions(t), [t])
  const deviceTypeLabels = useMemo(
    () => Object.fromEntries(deviceTypeOptions),
    [deviceTypeOptions],
  )

  const loadDevices = useCallback(async () => {
    setError(null)
    setRefreshing(true)
    try {
      const [deviceList, markers] = await Promise.all([getDevices(), getDeviceMap()])
      setDevices(Array.isArray(deviceList) ? deviceList : [])
      setMapData(Array.isArray(markers) ? markers : [])
      setLastUpdated(Date.now())
    } catch (err) {
      setError(getApiErrorMessage(err, t('devicesPage.loadFailed')))
    } finally {
      setRefreshing(false)
      setLoading(false)
    }
  }, [t])

  useEffect(() => {
    loadDevices()
  }, [loadDevices])

  const handleRegister = async () => {
    if (!form.device_id || !form.name) return
    setError(null)
    setSavingDevice(true)
    try {
      await registerDevice({
        device_id: form.device_id,
        name: form.name,
        latitude: form.latitude === '' ? null : parseFloat(form.latitude),
        longitude: form.longitude === '' ? null : parseFloat(form.longitude),
        type: form.type,
      })
      setShowForm(false)
      setForm({
        device_id: '',
        name: '',
        latitude: '',
        longitude: '',
        type: 'generic',
      })
      await loadDevices()
    } catch (err) {
      setError(getApiErrorMessage(err, t('devicesPage.registerFailed')))
    } finally {
      setSavingDevice(false)
    }
  }

  const handleRemove = async (deviceId) => {
    setError(null)
    setRemovingId(deviceId)
    try {
      await removeDevice(deviceId)
      await loadDevices()
    } catch (err) {
      setError(getApiErrorMessage(err, t('devicesPage.removeFailed')))
    } finally {
      setRemovingId(null)
    }
  }

  const onlineDevices = useMemo(() => devices.filter((device) => device.online), [devices])
  const offlineDevices = useMemo(() => devices.filter((device) => !device.online), [devices])
  const mappedDevices = mapData.length > 0 ? mapData : devices.filter(hasCoordinate)
  const lastUpdatedLabel = lastUpdated
    ? new Intl.DateTimeFormat(undefined, {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }).format(new Date(lastUpdated))
    : '--:--:--'

  if (loading) return <LoadingState text={t('devicesPage.loading')} />

  return (
    <div className="space-y-6">
      <PageHero
        kicker={(
          <>
            <Radio className="h-3.5 w-3.5" />
            {t('devicesPage.badge')}
          </>
        )}
        title={t('devicesPage.title')}
        body={t('devicesPage.body')}
        actions={(
          <>
            <button
              onClick={loadDevices}
              disabled={refreshing}
              className="touch-button flex items-center justify-center gap-1.5 rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-3 py-2 text-xs text-white/50 hover:bg-white/[0.08]"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
              {refreshing ? t('devicesPage.refreshing') : t('devicesPage.refresh')}
            </button>
            <button
              onClick={() => setShowForm((current) => !current)}
              className="touch-button flex items-center justify-center gap-1.5 rounded-[12px] border border-white/[0.06] bg-[#30D158]/15 px-3 py-2 text-xs text-[#30D158] hover:bg-[#30D158]/25"
            >
              <Cpu className="h-3.5 w-3.5" />
              {showForm ? t('devicesPage.hideForm') : t('devicesPage.registerDevice')}
            </button>
          </>
        )}
        metrics={(
          <>
            <StatCard label={t('devicesPage.registeredDevices')} value={devices.length} icon={Cpu} color="emerald" />
            <StatCard label={t('devicesPage.onlineNow')} value={onlineDevices.length} icon={Wifi} color="cyan" />
            <StatCard label={t('devicesPage.offlineNow')} value={offlineDevices.length} icon={WifiOff} color="amber" />
            <StatCard label={t('devicesPage.mappedLocations')} value={mappedDevices.length} icon={MapPin} color="violet" />
          </>
        )}
        aside={(
          <>
            <InfoNote title={t('devicesPage.notes.whyTitle')} body={t('devicesPage.notes.whyBody')} tone="emerald" />
            <InfoNote title={t('devicesPage.notes.focusTitle')} body={t('devicesPage.notes.focusBody')} tone="cyan" />
            <InfoNote title={t('devicesPage.notes.evidenceTitle')} body={t('devicesPage.notes.evidenceBody')} tone="amber" />
          </>
        )}
      />

      <div className="flex flex-wrap items-center gap-3 text-xs text-white/40">
        <span className="metric-chip">{t('devicesPage.lastSync', { time: lastUpdatedLabel })}</span>
        <span className="metric-chip">
          {refreshing ? t('devicesPage.querying') : t('devicesPage.syncState')}
        </span>
      </div>

      <StatusBanner tone="error" message={error} />

      {showForm && (
        <section className="section-shell space-y-4">
          <SectionHeader title={t('devicesPage.formTitle')} body={t('devicesPage.formBody')} />

          <div className="grid gap-3 md:grid-cols-2">
            <input
              value={form.device_id}
              onChange={(event) => setForm({ ...form, device_id: event.target.value })}
              placeholder={t('devicesPage.placeholders.deviceId')}
              className="rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-3 py-2 text-sm text-white placeholder-white/20"
            />
            <input
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
              placeholder={t('devicesPage.placeholders.name')}
              className="rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-3 py-2 text-sm text-white placeholder-white/20"
            />
            <input
              value={form.latitude}
              onChange={(event) => setForm({ ...form, latitude: event.target.value })}
              placeholder={t('devicesPage.placeholders.latitude')}
              type="number"
              step="0.0001"
              className="rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-3 py-2 text-sm text-white placeholder-white/20"
            />
            <input
              value={form.longitude}
              onChange={(event) => setForm({ ...form, longitude: event.target.value })}
              placeholder={t('devicesPage.placeholders.longitude')}
              type="number"
              step="0.0001"
              className="rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-3 py-2 text-sm text-white placeholder-white/20"
            />
            <select
              value={form.type}
              onChange={(event) => setForm({ ...form, type: event.target.value })}
              className="rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-3 py-2 text-sm text-white"
            >
              {deviceTypeOptions.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
            <button
              onClick={handleRegister}
              disabled={savingDevice || !form.device_id || !form.name}
              className="touch-button rounded-[12px] bg-[#30D158] px-4 py-2 text-sm font-medium text-white hover:bg-[#30D158]/80 disabled:opacity-50"
            >
              {savingDevice ? t('devicesPage.saving') : t('devicesPage.saveDevice')}
            </button>
          </div>
        </section>
      )}

      <section className="section-shell">
        <SectionHeader title={t('devicesPage.deviceMap')} body={t('devicesPage.deviceMapBody')} className="mb-4" />
        <div className="mobile-segmented mb-4 md:hidden">
          <button onClick={() => setMobilePanel('list')} data-active={mobilePanel === 'list'}>
            {t('devicesPage.deviceList')}
          </button>
          <button onClick={() => setMobilePanel('map')} data-active={mobilePanel === 'map'}>
            {t('devicesPage.mapView')}
          </button>
        </div>
        <div className={mobilePanel === 'map' ? 'block' : 'hidden md:block'}>
          <DeviceMap
            devices={mappedDevices}
            typeLabels={deviceTypeLabels}
            onlineLabel={t('devicesPage.online')}
            offlineLabel={t('devicesPage.offline')}
            loadingLabel={t('devicesPage.loadingMap')}
          />
        </div>
      </section>

      <section className={`space-y-3 ${mobilePanel === 'list' ? 'block' : 'hidden md:block'}`}>
        {devices.length === 0 ? (
          <EmptyPanel icon={Cpu} title={t('devicesPage.noDevices')} body={t('devicesPage.noDevicesBody')} />
        ) : (
          devices.map((device) => (
            <div key={device.device_id} className="surface-card flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div className="flex items-center gap-3">
                <div className={`h-2.5 w-2.5 rounded-full ${device.online ? 'bg-[#30D158]' : 'bg-white/20'}`} />
                <div>
                  <p className="text-sm font-medium text-white">{device.name || device.device_id}</p>
                  <p className="text-xs text-white/25">
                    {device.device_id} · {deviceTypeLabels[device.type] || device.type || deviceTypeLabels.generic}
                  </p>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-3 md:justify-end">
                {hasCoordinate(device) && (
                  <span className="text-xs text-white/25">
                    {Number(device.latitude).toFixed(4)}, {Number(device.longitude).toFixed(4)}
                  </span>
                )}
                <span
                  className={`rounded-full px-2.5 py-1 text-xs ${
                    device.online
                      ? 'bg-[#30D158]/15 text-[#30D158]'
                      : 'bg-white/[0.06] text-white/30'
                  }`}
                >
                  {device.online ? t('devicesPage.online') : t('devicesPage.offline')}
                </span>
                <button
                  onClick={() => handleRemove(device.device_id)}
                  disabled={removingId === device.device_id}
                  className="touch-button rounded-[12px] border border-white/[0.06] px-2.5 text-[#FF453A]/60 transition-colors hover:bg-[#FF453A]/10 hover:text-[#FF453A] disabled:opacity-40"
                  title={t('devicesPage.removeDevice')}
                >
                  {removingId === device.device_id ? <Loader2 className="h-4 w-4 animate-spin" /> : <X className="h-4 w-4" />}
                </button>
              </div>
            </div>
          ))
        )}
      </section>
    </div>
  )
}

function DeviceMap({ devices, typeLabels, onlineLabel, offlineLabel, loadingLabel }) {
  const mapRef = useRef(null)
  const [mapReady, setMapReady] = useState(false)

  useEffect(() => {
    if (mapRef.current || typeof window === 'undefined') return undefined

    import('leaflet').then((L) => {
      delete L.Icon.Default.prototype._getIconUrl
      L.Icon.Default.mergeOptions({
        iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
        iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
        shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
      })

      const map = L.map('device-map').setView([28, 108], 4)
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors',
        maxZoom: 18,
      }).addTo(map)
      mapRef.current = map
      setMapReady(true)
    }).catch((err) => console.error('[map] Failed to load map library:', err))

    return () => {
      if (mapRef.current) {
        mapRef.current.remove()
        mapRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    if (!mapReady || !mapRef.current) return

    import('leaflet').then((L) => {
      mapRef.current.eachLayer((layer) => {
        if (layer instanceof L.Marker) mapRef.current.removeLayer(layer)
      })

      const validDevices = (devices || []).filter(hasCoordinate)

      validDevices.forEach((device) => {
        const lat = Number(device.latitude)
        const lon = Number(device.longitude)

        const icon = L.divIcon({
          className: '',
          html: `<div style="width:12px;height:12px;border-radius:50%;background:${device.online ? '#10b981' : '#ef4444'};border:2px solid white;box-shadow:0 0 6px rgba(0,0,0,0.35)"></div>`,
          iconSize: [12, 12],
          iconAnchor: [6, 6],
        })

        const typeLabel = typeLabels[device.type] || device.type || typeLabels.generic || 'ARU'
        const statusLabel = device.online ? onlineLabel : offlineLabel

        L.marker([lat, lon], { icon }).addTo(mapRef.current).bindPopup(`
          <div style="font-size:12px">
            <b>${device.name || device.device_id}</b><br/>
            ${typeLabel} · ${statusLabel}<br/>
            <span style="color:#888">${lat.toFixed(4)}, ${lon.toFixed(4)}</span>
          </div>
        `)
      })

      if (validDevices.length > 0) {
        const bounds = L.latLngBounds(validDevices.map((device) => [Number(device.latitude), Number(device.longitude)]))
        mapRef.current.fitBounds(bounds, { padding: [50, 50], maxZoom: 12 })
      }
    }).catch((err) => console.error('[map] Failed to load map library:', err))
  }, [devices, mapReady, offlineLabel, onlineLabel, typeLabels])

  return (
    <div id="device-map" className="h-72 overflow-hidden rounded-2xl border border-white/[0.06]" style={{ background: '#1a1a2e' }}>
      {!mapReady && (
        <div className="flex h-full items-center justify-center text-sm text-white/25">
          <Loader2 className="mr-2 h-5 w-5 animate-spin" />
          {loadingLabel}
        </div>
      )}
    </div>
  )
}
