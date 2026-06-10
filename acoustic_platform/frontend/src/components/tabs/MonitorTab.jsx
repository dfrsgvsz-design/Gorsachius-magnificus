import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Activity,
  Bird,
  Clock,
  Loader2,
  MapPin,
  Mic,
  Plus,
  Radio,
  RefreshCw,
  Router,
  Shield,
  Trash2,
  Trees,
} from 'lucide-react'
import {
  createSurveySite,
  getApiErrorMessage,
  getMonitoringDashboard,
  getMonitoringSessions,
  getSurveySites,
  removeSurveySite,
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

function formatDuration(seconds) {
  if (!seconds && seconds !== 0) return '--'
  const total = Math.max(0, Math.round(seconds))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const remaining = total % 60

  if (hours > 0) return `${hours}h ${minutes}m`
  if (minutes > 0) return `${minutes}m ${remaining}s`
  return `${remaining}s`
}

export default function MonitorTab() {
  const { t } = useTranslation()
  const [dashboard, setDashboard] = useState(null)
  const [sessions, setSessions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [refreshing, setRefreshing] = useState(false)
  const [lastUpdated, setLastUpdated] = useState(null)
  const [surveySites, setSurveySites] = useState([])

  const loadData = useCallback(async () => {
    setError(null)
    setRefreshing(true)
    try {
      const [summary, activeSessions] = await Promise.all([
        getMonitoringDashboard(),
        getMonitoringSessions(),
      ])
      setDashboard(summary || null)
      setSessions(Array.isArray(activeSessions) ? activeSessions : [])
      setLastUpdated(Date.now())
    } catch (err) {
      setError(getApiErrorMessage(err, t('monitorPage.loadFailed')))
    } finally {
      setRefreshing(false)
      setLoading(false)
    }
  }, [t])

  useEffect(() => {
    loadData()
    const interval = setInterval(() => {
      if (document.visibilityState === 'visible') loadData()
    }, 10000)
    return () => clearInterval(interval)
  }, [loadData])

  const topSpecies = dashboard?.detections?.top_species || []
  const activeSessions = sessions.length
  const totalDetections = dashboard?.total_detections || 0
  const totalSpecies = dashboard?.unique_species || 0
  const onlineDevices = dashboard?.devices?.online || 0
  const monitoringMode = dashboard?.mode === 'active'
    ? t('monitorPage.modeActive')
    : t('monitorPage.modeIdle')
  const lastUpdatedLabel = lastUpdated
    ? new Intl.DateTimeFormat(undefined, {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }).format(new Date(lastUpdated))
    : '--:--:--'

  const timelineSummary = useMemo(() => {
    const durations = sessions.map((session) => session.duration_seconds || 0)
    const longestSession = durations.length > 0 ? Math.max(...durations) : 0
    const totalSegments = sessions.reduce((sum, session) => sum + (session.total_segments || 0), 0)
    return { longestSession, totalSegments }
  }, [sessions])

  if (loading) return <LoadingState text={t('monitorPage.loading')} />

  return (
    <div className="space-y-6">
      <PageHero
        kicker={(
          <>
            <Radio className="h-3.5 w-3.5" />
            {t('monitorPage.badge')}
          </>
        )}
        title={t('monitorPage.title')}
        body={t('monitorPage.body')}
        actions={(
          <div className="flex flex-col gap-2 self-start rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-xs text-gray-400 sm:flex-row sm:items-center">
            <div className="flex items-center gap-2">
              <span className="pulse-dot inline-block h-2 w-2 rounded-full bg-emerald-400"></span>
              {t('monitorPage.autoRefresh')}
            </div>
            <button
              onClick={loadData}
              disabled={refreshing}
              className="touch-button inline-flex items-center justify-center gap-1 rounded-full border border-white/10 bg-white/5 px-2 py-1 text-[11px] text-gray-300 hover:bg-white/10"
            >
              <RefreshCw className={`h-3 w-3 ${refreshing ? 'animate-spin' : ''}`} />
              {refreshing ? t('monitorPage.refreshing') : t('monitorPage.refreshNow')}
            </button>
          </div>
        )}
        metrics={(
          <>
            <StatCard label={t('monitorPage.activeSessions')} value={activeSessions} icon={Activity} color="teal" />
            <StatCard label={t('monitorPage.detectionEvents')} value={totalDetections} icon={Mic} color="blue" />
            <StatCard label={t('monitorPage.uniqueSpecies')} value={totalSpecies} icon={Bird} color="forest" />
            <StatCard label={t('monitorPage.onlineDevices')} value={onlineDevices} icon={Router} color="amber" />
          </>
        )}
        aside={(
          <>
            <InfoNote
              title={t('monitorPage.monitoringMode')}
              body={t('monitorPage.monitoringModeBody', { mode: monitoringMode })}
              tone="emerald"
            />
            <InfoNote title={t('monitorPage.longestSession')} body={formatDuration(timelineSummary.longestSession)} tone="cyan" />
            <InfoNote
              title={t('monitorPage.bufferedSegments')}
              body={t('monitorPage.bufferedSegmentsBody', { count: timelineSummary.totalSegments })}
              tone="amber"
            />
          </>
        )}
      />

      <div className="flex flex-wrap items-center gap-3 text-xs text-gray-400">
        <span className="metric-chip">{t('monitorPage.lastSync', { time: lastUpdatedLabel })}</span>
        <span className="metric-chip">
          {refreshing ? t('monitorPage.polling') : t('monitorPage.syncState')}
        </span>
      </div>

      <StatusBanner tone="error" message={error} />

      <section className="grid gap-3 md:gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="section-shell">
          <SectionHeader
            title={t('monitorPage.sessionsTitle')}
            body={t('monitorPage.sessionsBody')}
            action={<span className="metric-chip">{t('monitorPage.activeCount', { count: activeSessions })}</span>}
          />

          {sessions.length === 0 ? (
            <EmptyPanel icon={Radio} title={t('monitorPage.noSessions')} body={t('monitorPage.noSessionsBody')} />
          ) : (
            <div className="mt-3 space-y-2 md:mt-4 md:space-y-3">
              {sessions.map((session, index) => (
                <div key={session.session_id || index} className="rounded-xl border border-white/10 bg-white/5 p-3 md:p-4">
                  <div className="flex items-start justify-between gap-2 md:flex-row md:items-center">
                    <div className="min-w-0">
                      <p className="truncate text-xs font-semibold text-white md:text-sm">
                        {session.session_id || t('monitorPage.sessionLabel', { index: index + 1 })}
                      </p>
                      <p className="mt-0.5 text-[11px] text-gray-500 md:mt-1 md:text-xs">
                        {t('monitorPage.sessionMeta', {
                          device: session.device_id || '--',
                          duration: formatDuration(session.duration_seconds),
                        })}
                      </p>
                    </div>
                    <span className="shrink-0 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[11px] text-emerald-300 md:px-2.5 md:py-1 md:text-xs">
                      {session.status || 'active'}
                    </span>
                  </div>

                  <div className="mt-2 grid grid-cols-3 gap-1.5 md:mt-3 md:gap-2">
                    <SessionStat label={t('monitorPage.species')} value={session.species_count || session.unique_species || 0} />
                    <SessionStat label={t('monitorPage.detections')} value={session.detection_count || session.total_detections || 0} />
                    <SessionStat label={t('monitorPage.segments')} value={session.total_segments || 0} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="section-shell">
          <SectionHeader title={t('monitorPage.topSpeciesTitle')} body={t('monitorPage.topSpeciesBody')} />

          {topSpecies.length === 0 ? (
            <EmptyPanel icon={Clock} title={t('monitorPage.noTopSpecies')} body={t('monitorPage.noTopSpeciesBody')} />
          ) : (
            <div className="mt-3 space-y-1.5 md:mt-4 md:space-y-2">
              {topSpecies.slice(0, 10).map(([species, count], index) => (
                <div key={`${species}-${index}`} className="flex items-center justify-between gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 md:gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-xs font-medium text-emerald-300 md:text-sm">{species}</p>
                    <p className="text-[11px] text-gray-500 md:text-xs">{t('monitorPage.ranking', { index: index + 1 })}</p>
                  </div>
                  <span className="shrink-0 rounded-full border border-cyan-500/20 bg-cyan-500/10 px-2 py-0.5 text-[11px] text-cyan-300 md:px-2.5 md:py-1 md:text-xs">
                    {t('monitorPage.events', { count })}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      <section className="section-shell">
        <SectionHeader title={t('monitorPage.whyTitle')} />
        <div className="mt-3 grid gap-2 md:mt-4 md:gap-4 lg:grid-cols-3">
          <MonitorReason
            icon={Shield}
            title={t('monitorPage.reasons.continuityTitle')}
            body={t('monitorPage.reasons.continuityBody')}
          />
          <MonitorReason
            icon={Mic}
            title={t('monitorPage.reasons.powerTitle')}
            body={t('monitorPage.reasons.powerBody')}
          />
          <MonitorReason
            icon={Bird}
            title={t('monitorPage.reasons.speciesTitle')}
            body={t('monitorPage.reasons.speciesBody')}
          />
        </div>
      </section>

      <DetectionMap sites={surveySites} />
      <SurveySiteManager onSitesChange={setSurveySites} />
    </div>
  )
}

function SurveySiteManager({ onSitesChange }) {
  const { t } = useTranslation()
  const [sites, setSites] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [saving, setSaving] = useState(false)
  const [removingName, setRemovingName] = useState(null)
  const [error, setError] = useState(null)
  const [form, setForm] = useState({
    site_name: '', region: '', latitude: '', longitude: '', habitat_type: '', protocol: 'point_count', notes: '',
  })

  const loadSites = useCallback(async () => {
    try {
      const data = await getSurveySites()
      const loaded = data.sites || []
      setSites(loaded)
      onSitesChange?.(loaded)
    } catch { /* empty */ } finally {
      setLoading(false)
    }
  }, [onSitesChange])

  useEffect(() => { loadSites() }, [loadSites])

  const handleCreate = async () => {
    if (!form.site_name) return
    setSaving(true)
    setError(null)
    try {
      await createSurveySite({
        ...form,
        latitude: form.latitude ? Number(form.latitude) : null,
        longitude: form.longitude ? Number(form.longitude) : null,
      })
      setForm({ site_name: '', region: '', latitude: '', longitude: '', habitat_type: '', protocol: 'point_count', notes: '' })
      setShowForm(false)
      await loadSites()
    } catch (err) {
      setError(getApiErrorMessage(err, t('monitorPage.createSiteFailed', { defaultValue: 'Failed to create site' })))
    } finally { setSaving(false) }
  }

  const handleRemove = async (name) => {
    setRemovingName(name)
    try {
      await removeSurveySite(name)
      await loadSites()
    } catch { /* empty */ } finally { setRemovingName(null) }
  }

  return (
    <section className="section-shell space-y-3 md:space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-sm font-semibold text-white md:text-base">
            <Trees className="h-4 w-4 text-emerald-400" />
            {t('monitorPage.surveySites') || 'Survey Sites'}
          </h3>
          <p className="mt-1 text-xs text-slate-400 md:text-sm">
            {t('monitorPage.surveySitesDesc') || 'Manage field survey sites for systematic acoustic monitoring across regions.'}
          </p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="touch-button flex shrink-0 items-center gap-1 rounded-lg border border-emerald-500/25 bg-emerald-500/10 px-2.5 py-1.5 text-[11px] text-emerald-300 active:scale-[0.97] md:text-xs"
        >
          <Plus className="h-3 w-3" />
          <span className="hidden sm:inline">
            {showForm
              ? t('common.cancel', { defaultValue: 'Cancel' })
              : t('monitorPage.addSite', { defaultValue: 'Add site' })}
          </span>
        </button>
      </div>

      {error && <p className="rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-2 text-xs text-red-300">{error}</p>}

      {showForm && (
        <div className="grid gap-2 rounded-xl border border-white/10 bg-white/[0.04] p-3 md:grid-cols-2 md:gap-3 md:p-4">
          <input value={form.site_name} onChange={(e) => setForm({ ...form, site_name: e.target.value })} placeholder={t('monitorPage.siteNamePlaceholder', { defaultValue: 'Site name *' })} className="touch-button rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-gray-500" />
          <input value={form.region} onChange={(e) => setForm({ ...form, region: e.target.value })} placeholder={t('monitorPage.regionPlaceholder', { defaultValue: 'Region (e.g. Guangxi)' })} className="touch-button rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-gray-500" />
          <input value={form.latitude} onChange={(e) => setForm({ ...form, latitude: e.target.value })} placeholder={t('monitorPage.latitude', { defaultValue: 'Latitude' })} type="number" step="0.0001" className="touch-button rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-gray-500" />
          <input value={form.longitude} onChange={(e) => setForm({ ...form, longitude: e.target.value })} placeholder={t('monitorPage.longitude', { defaultValue: 'Longitude' })} type="number" step="0.0001" className="touch-button rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-gray-500" />
          <select value={form.habitat_type} onChange={(e) => setForm({ ...form, habitat_type: e.target.value })} className="touch-button rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white">
            <option value="">{t('monitorPage.habitatType', { defaultValue: 'Habitat type' })}</option>
            <option value="forest">{t('monitorPage.habitatForest', { defaultValue: 'Forest' })}</option>
            <option value="wetland">{t('monitorPage.habitatWetland', { defaultValue: 'Wetland' })}</option>
            <option value="grassland">{t('monitorPage.habitatGrassland', { defaultValue: 'Grassland' })}</option>
            <option value="urban">{t('monitorPage.habitatUrban', { defaultValue: 'Urban' })}</option>
            <option value="agricultural">{t('monitorPage.habitatAgricultural', { defaultValue: 'Agricultural' })}</option>
            <option value="montane">{t('monitorPage.habitatMontane', { defaultValue: 'Montane' })}</option>
          </select>
          <select value={form.protocol} onChange={(e) => setForm({ ...form, protocol: e.target.value })} className="touch-button rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white">
            <option value="point_count">{t('monitorPage.protocolPointCount', { defaultValue: 'Point count' })}</option>
            <option value="transect">{t('monitorPage.protocolTransect', { defaultValue: 'Transect' })}</option>
            <option value="aru_continuous">{t('monitorPage.protocolAruContinuous', { defaultValue: 'ARU continuous' })}</option>
            <option value="aru_scheduled">{t('monitorPage.protocolAruScheduled', { defaultValue: 'ARU scheduled' })}</option>
          </select>
          <textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} placeholder={t('common.notes', { defaultValue: 'Notes' })} rows={2} className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-gray-500 md:col-span-2" />
          <button onClick={handleCreate} disabled={saving || !form.site_name} className="touch-button rounded-lg bg-emerald-500 px-4 py-2 text-sm font-medium text-white active:scale-[0.97] disabled:opacity-50 md:col-span-2">
            {saving
              ? t('monitorPage.creatingSite', { defaultValue: 'Creating...' })
              : t('monitorPage.createSite', { defaultValue: 'Create site' })}
          </button>
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-6"><Loader2 className="h-5 w-5 animate-spin text-gray-400" /></div>
      ) : sites.length === 0 ? (
        <div className="rounded-xl border border-white/10 bg-white/[0.04] py-8 text-center">
          <MapPin className="mx-auto mb-2 h-8 w-8 text-gray-600" />
          <p className="text-xs text-gray-400">
            {t('monitorPage.noSurveySites', { defaultValue: 'No survey sites registered yet.' })}
          </p>
        </div>
      ) : (
        <div className="space-y-1.5 md:space-y-2">
          {sites.map((site) => (
            <div key={site.site_name} className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/[0.04] p-3 md:p-4">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-medium text-white">{site.site_name}</p>
                  {site.region && <span className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] text-gray-400">{site.region}</span>}
                  {site.habitat_type && <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[10px] text-emerald-300">{site.habitat_type}</span>}
                </div>
                <div className="mt-1 flex flex-wrap gap-3 text-[11px] text-gray-500">
                  <span>{t('monitorPage.protocol', { defaultValue: 'Protocol' })}: {site.protocol?.replace('_', ' ')}</span>
                  {site.latitude != null && <span>{Number(site.latitude).toFixed(4)}, {Number(site.longitude).toFixed(4)}</span>}
                  <span>{t('monitorPage.detections', { defaultValue: 'Detections' })}: {site.total_detections || 0}</span>
                  <span>{t('monitorPage.species', { defaultValue: 'Species' })}: {site.species_detected || 0}</span>
                </div>
              </div>
              <button onClick={() => handleRemove(site.site_name)} disabled={removingName === site.site_name} className="touch-button shrink-0 rounded-lg border border-red-500/20 p-2 text-red-400/60 active:scale-[0.95] disabled:opacity-40">
                {removingName === site.site_name ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

function detectionCountColor(count) {
  const n = Number(count) || 0
  if (n <= 0) return '#64748b'
  if (n < 10) return '#22c55e'
  if (n < 50) return '#eab308'
  if (n < 200) return '#f97316'
  return '#ef4444'
}

function escapeHtml(str) {
  if (str == null) return ''
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function DetectionMap({ sites: sitesFromParent = [] }) {
  const { t } = useTranslation()
  const mapElRef = useRef(null)
  const mapRef = useRef(null)
  const leafletRef = useRef(null)
  const markersGroupRef = useRef(null)
  const sitesRef = useRef([])
  const [sites, setSites] = useState([])

  sitesRef.current = sites

  useEffect(() => {
    if (sitesFromParent.length > 0) {
      setSites(sitesFromParent)
      return undefined
    }
    let cancelled = false
    ;(async () => {
      try {
        const data = await getSurveySites()
        if (!cancelled) setSites(data.sites || [])
      } catch {
        if (!cancelled) setSites([])
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const syncMarkers = useCallback(() => {
    const L = leafletRef.current
    const map = mapRef.current
    const group = markersGroupRef.current
    if (!L || !map || !group) return

    group.clearLayers()

    sitesRef.current.forEach((site) => {
      const lat = site.latitude != null ? Number(site.latitude) : NaN
      const lng = site.longitude != null ? Number(site.longitude) : NaN
      if (!Number.isFinite(lat) || !Number.isFinite(lng)) return

      const count = site.total_detections || 0
      const color = detectionCountColor(count)
      const icon = L.divIcon({
        className: 'leaflet-div-icon detection-map-marker-wrap',
        html: `<div class="detection-map-marker-dot" style="width:14px;height:14px;border-radius:50%;background:${color};border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,0.45)"></div>`,
        iconSize: [14, 14],
        iconAnchor: [7, 7],
      })

      const marker = L.marker([lat, lng], { icon })
      const name = escapeHtml(site.site_name || '')
      marker.bindPopup(
        `<div style="min-width:140px"><strong>${name}</strong><br/><span style="color:#334155">${escapeHtml(t('monitorPage.detections', { defaultValue: 'Detections' }))}: ${count}</span></div>`,
      )
      group.addLayer(marker)
    })
  }, [])

  useEffect(() => {
    const el = mapElRef.current
    if (!el) return undefined

    let cancelled = false

    Promise.all([import('leaflet'), import('leaflet/dist/leaflet.css')]).then(([leafletMod]) => {
      if (cancelled || !mapElRef.current) return
      const L = leafletMod.default
      leafletRef.current = L

      const map = L.map(el, {
        center: [23, 108],
        zoom: 6,
        scrollWheelZoom: true,
      })

      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      }).addTo(map)

      const group = L.layerGroup().addTo(map)
      markersGroupRef.current = group
      mapRef.current = map

      syncMarkers()
      map.invalidateSize()
    }).catch((err) => console.error('[map] Failed to load map library:', err))

    return () => {
      cancelled = true
      markersGroupRef.current = null
      leafletRef.current = null
      if (mapRef.current) {
        mapRef.current.remove()
        mapRef.current = null
      }
    }
  }, [syncMarkers])

  useEffect(() => {
    syncMarkers()
  }, [sites, syncMarkers])

  return (
    <section className="section-shell space-y-3">
      <style>
        {`#detection-map .detection-map-marker-wrap.leaflet-div-icon{background:transparent!important;border:none!important;}`}
      </style>
      <div className="flex items-center gap-2 text-sm font-semibold text-white md:text-base">
        <MapPin className="h-4 w-4 text-cyan-400" />
        {t('monitorPage.detectionMapTitle', { defaultValue: 'Detection Distribution Map' })}
      </div>
      <div
        id="detection-map"
        ref={mapElRef}
        className="w-full overflow-hidden rounded-xl border border-white/10"
        style={{ height: 300 }}
      />
    </section>
  )
}

function SessionStat({ label, value }) {
  return (
    <div className="rounded-lg border px-2 py-1.5 md:px-3 md:py-2" style={{ borderColor: 'var(--border-subtle)', background: 'var(--surface-secondary)' }}>
      <p className="text-[10px] uppercase tracking-[0.14em] md:text-[11px] md:tracking-[0.16em]" style={{ color: 'var(--text-tertiary)' }}>{label}</p>
      <p className="mt-0.5 text-base font-semibold md:mt-1 md:text-lg" style={{ color: 'var(--text-primary)' }}>{value}</p>
    </div>
  )
}

function MonitorReason({ icon: Icon, title, body }) {
  return (
    <div className="rounded-xl border p-3 md:p-4" style={{ borderColor: 'var(--border-default)', background: 'var(--surface-secondary)' }}>
      <div className="flex items-center gap-2 text-xs font-medium md:text-sm" style={{ color: 'var(--text-primary)' }}>
        <Icon className="h-3.5 w-3.5 md:h-4 md:w-4" style={{ color: 'var(--cornell-blue)' }} />
        {title}
      </div>
      <p className="mt-1.5 text-xs leading-5 md:mt-2 md:text-sm md:leading-6" style={{ color: 'var(--text-secondary)' }}>{body}</p>
    </div>
  )
}
