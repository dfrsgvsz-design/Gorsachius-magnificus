import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AlertTriangle, BarChart3, Flame, Layers, Loader2, MapPin, Mic, ShieldCheck, Trees } from 'lucide-react'
import { getGBIFOccurrences, getINatObservations } from '../../lib/api'
import { usePlatformConfig } from '../../lib/PlatformConfigContext'

const MODEL_KEYS = [
  'targetSpecies',
  'modelingApproach',
  'occurrenceRecords',
  'predictorStack',
  'spatialResolution',
  'validationApproach',
]

const CLIMATE_KEYS = [
  { key: 'current', tone: 'text-white' },
  { key: 'ssp126', tone: 'text-amber-300' },
  { key: 'ssp245', tone: 'text-amber-300' },
  { key: 'ssp585', tone: 'text-red-300' },
  { key: 'refugia', tone: 'text-emerald-300' },
]

const INTEGRATION_KEYS = [
  { key: 'integPrioritize', descKey: 'integPrioritizeDesc', icon: MapPin, tone: 'emerald' },
  { key: 'integValidate', descKey: 'integValidateDesc', icon: Mic, tone: 'cyan' },
  { key: 'integOccupancy', descKey: 'integOccupancyDesc', icon: BarChart3, tone: 'violet' },
]

const PRIORITY_SITES = [
  {
    nameKey: 'Guangxi Nonggang National Nature Reserve',
    nameZh: '广西弄岗国家级自然保护区',
    lat: 22.45,
    lon: 106.96,
    priority: 'priorityVeryHigh',
    reasonKey: 'High suitability and known breeding records',
    reasonZh: '高适宜性且有已知繁殖记录',
  },
  {
    nameKey: 'Guizhou Maolan National Nature Reserve',
    nameZh: '贵州茂兰国家级自然保护区',
    lat: 25.31,
    lon: 107.98,
    priority: 'priorityVeryHigh',
    reasonKey: 'High suitability with intact karst forest habitat',
    reasonZh: '高适宜性，保存完好的喀斯特森林栖息地',
  },
  {
    nameKey: 'Guangdong Nanling National Nature Reserve',
    nameZh: '广东南岭国家级自然保护区',
    lat: 24.92,
    lon: 112.93,
    priority: 'priorityHigh',
    reasonKey: 'Moderate suitability with historical records',
    reasonZh: '中等适宜性，有历史记录',
  },
  {
    nameKey: 'Jiangxi Wuyishan National Park',
    nameZh: '江西武夷山国家公园',
    lat: 27.75,
    lon: 117.73,
    priority: 'priorityHigh',
    reasonKey: 'Potential newly suitable area requiring acoustic confirmation',
    reasonZh: '潜在新增适宜区域，需要声学确认',
  },
  {
    nameKey: 'Fujian Meihuashan National Nature Reserve',
    nameZh: '福建梅花山国家级自然保护区',
    lat: 25.48,
    lon: 116.8,
    priority: 'priorityMedium',
    reasonKey: 'Peripheral suitability with limited recent survey effort',
    reasonZh: '边缘适宜性，近期调查力度有限',
  },
]

const DETECTION_POINTS = [
  { id: 'det-1', lat: 22.45, lon: 106.96, weight: 0.95, source: 'local' },
  { id: 'det-2', lat: 25.31, lon: 107.98, weight: 0.88, source: 'local' },
  { id: 'det-3', lat: 24.92, lon: 112.93, weight: 0.62, source: 'local' },
  { id: 'det-4', lat: 27.75, lon: 117.73, weight: 0.5, source: 'local' },
  { id: 'det-5', lat: 25.48, lon: 116.8, weight: 0.44, source: 'local' },
]

export default function SDMTab() {
  const { t, i18n } = useTranslation()
  const isZh = i18n.resolvedLanguage?.startsWith('zh')

  const [showHeatmap, setShowHeatmap] = useState(true)
  const [showDetections, setShowDetections] = useState(true)
  const [showGbif, setShowGbif] = useState(true)
  const [showInat, setShowInat] = useState(true)
  const [gbifPoints, setGbifPoints] = useState([])
  const [inatPoints, setInatPoints] = useState([])
  const [loadingExternal, setLoadingExternal] = useState(false)
  const platformConfig = usePlatformConfig()
  const speciesQuery = platformConfig.target_species?.gbif_query || platformConfig.target_species?.scientific_name || 'Gorsachius magnificus'
  const countryCode = platformConfig.study_region?.country_code || 'CN'

  const loadExternalData = useCallback(async () => {
    setLoadingExternal(true)
    try {
      const [gbifData, inatData] = await Promise.allSettled([
        getGBIFOccurrences(speciesQuery, countryCode, 50),
        getINatObservations(speciesQuery, null, null, 50),
      ])

      if (gbifData.status === 'fulfilled' && gbifData.value?.results) {
        setGbifPoints(
          gbifData.value.results
            .filter((r) => r.decimalLatitude != null && r.decimalLongitude != null)
            .map((r, i) => ({ id: `gbif-${i}`, lat: r.decimalLatitude, lon: r.decimalLongitude }))
        )
      }

      if (inatData.status === 'fulfilled') {
        const obs = inatData.value?.results || inatData.value?.observations || []
        setInatPoints(
          obs
            .filter((o) => o.location || (o.geojson?.coordinates))
            .map((o, i) => {
              const coords = o.location?.split(',') || o.geojson?.coordinates?.slice().reverse() || []
              return { id: `inat-${i}`, lat: parseFloat(coords[0]) || 0, lon: parseFloat(coords[1]) || 0 }
            })
            .filter((p) => p.lat !== 0 && p.lon !== 0)
        )
      }
    } catch {
      // silent - will show static fallback points if any
    } finally {
      setLoadingExternal(false)
    }
  }, [speciesQuery, countryCode])

  useEffect(() => { loadExternalData() }, [loadExternalData])

  const mapRef = useRef(null)
  const layerRef = useRef({})
  const mapId = 'sdm-overlays-map'
  const pointsCenter = useMemo(
    () => [platformConfig.study_region?.center_lat || 24.7, platformConfig.study_region?.center_lon || 110.5],
    [platformConfig],
  )

  useEffect(() => {
    if (mapRef.current || typeof window === 'undefined') return undefined
    let mounted = true

    import('leaflet').then((L) => {
      if (!mounted) return
      const map = L.map(mapId).setView(pointsCenter, 5)
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors',
        maxZoom: 18,
      }).addTo(map)
      mapRef.current = map
    })

    return () => {
      mounted = false
      if (mapRef.current) {
        mapRef.current.remove()
        mapRef.current = null
      }
    }
  }, [pointsCenter])

  useEffect(() => {
    if (!mapRef.current) return
    import('leaflet').then((L) => {
      Object.values(layerRef.current).forEach((layerGroup) => {
        if (layerGroup) mapRef.current.removeLayer(layerGroup)
      })

      const heatLayer = L.layerGroup()
      DETECTION_POINTS.forEach((point) => {
        const radius = 8000 + point.weight * 18000
        L.circle([point.lat, point.lon], {
          radius,
          color: 'transparent',
          fillColor: '#ef4444',
          fillOpacity: 0.1 + point.weight * 0.35,
        }).addTo(heatLayer)
      })

      const detectionLayer = L.layerGroup()
      DETECTION_POINTS.forEach((point) => {
        L.circleMarker([point.lat, point.lon], {
          radius: 4 + point.weight * 8,
          color: '#10b981',
          fillColor: '#10b981',
          fillOpacity: 0.7,
          weight: 1,
        }).bindPopup(t('sdmPage.detectionWeight', { weight: point.weight.toFixed(2) })).addTo(detectionLayer)
      })

      const gbifLayer = L.layerGroup()
      gbifPoints.forEach((point) => {
        L.circleMarker([point.lat, point.lon], {
          radius: 5,
          color: '#3b82f6',
          fillColor: '#3b82f6',
          fillOpacity: 0.65,
          weight: 1,
        }).bindPopup(t('sdmPage.gbifOccurrence')).addTo(gbifLayer)
      })

      const inatLayer = L.layerGroup()
      inatPoints.forEach((point) => {
        L.circleMarker([point.lat, point.lon], {
          radius: 5,
          color: '#f59e0b',
          fillColor: '#f59e0b',
          fillOpacity: 0.65,
          weight: 1,
        }).bindPopup(t('sdmPage.inatObservation')).addTo(inatLayer)
      })

      layerRef.current = { heatLayer, detectionLayer, gbifLayer, inatLayer }

      if (showHeatmap) heatLayer.addTo(mapRef.current)
      if (showDetections) detectionLayer.addTo(mapRef.current)
      if (showGbif) gbifLayer.addTo(mapRef.current)
      if (showInat) inatLayer.addTo(mapRef.current)
    })
  }, [showDetections, showGbif, showHeatmap, showInat, gbifPoints, inatPoints, t])

  const priorityTone = {
    priorityVeryHigh: 'bg-red-500/20 text-red-300',
    priorityHigh: 'bg-amber-500/20 text-amber-300',
    priorityMedium: 'bg-cyan-500/20 text-cyan-300',
  }

  return (
    <div className="space-y-6">
      <section className="glass-card space-y-5 p-6">
        <div className="max-w-3xl">
          <div className="inline-flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-medium text-emerald-300">
            <Trees className="h-3.5 w-3.5" />
            {t('sdmPage.badge')}
          </div>
          <h2 className="mt-3 text-2xl font-bold text-white">{t('sdmPage.title')}</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-gray-300">{t('sdmPage.body')}</p>
        </div>

        <div className="grid gap-4 lg:grid-cols-3">
          <SdmNote title={t('sdmPage.noteContributes')} body={t('sdmPage.noteContributesBody')} />
          <SdmNote title={t('sdmPage.noteCannotReplace')} body={t('sdmPage.noteCannotReplaceBody')} />
          <SdmNote title={t('sdmPage.noteWhyMatters')} body={t('sdmPage.noteWhyMattersBody')} />
        </div>
      </section>

      <section className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4">
        <div className="flex items-start gap-3">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
          <div>
            <p className="text-sm font-medium text-amber-300">
              {t('sdmPage.demoBannerTitle', 'Illustrative Data')}
            </p>
            <p className="mt-1 text-xs leading-5 text-amber-200/80">
              {t('sdmPage.demoBannerBody', 'The heatmap, detection points, and priority sites shown below are illustrative examples based on literature and expert knowledge — not outputs from a connected SDM pipeline. GBIF and iNaturalist occurrences are fetched live when available.')}
            </p>
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2">
        <div className="glass-card p-5">
          <h3 className="text-sm font-semibold text-white">{t('sdmPage.modelOverview')}</h3>
          <div className="mt-4 space-y-2 text-sm">
            {MODEL_KEYS.map((key) => (
              <div key={key} className="flex items-center justify-between rounded-lg bg-white/5 px-3 py-2">
                <span className="text-gray-400">{t(`sdmPage.modelFields.${key}`)}</span>
                <span className="text-white">{t(`sdmPage.modelValues.${key}`)}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="glass-card p-5">
          <h3 className="text-sm font-semibold text-white">{t('sdmPage.climateScenario')}</h3>
          <div className="mt-4 space-y-2 text-sm">
            {CLIMATE_KEYS.map(({ key, tone }) => (
              <div key={key} className="flex items-center justify-between rounded-lg bg-white/5 px-3 py-2">
                <span className="text-gray-400">{t(`sdmPage.climateFields.${key}`)}</span>
                <span className={tone}>{t(`sdmPage.climateValues.${key}`)}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="glass-card p-5">
        <h3 className="text-sm font-semibold text-white">{t('sdmPage.howFits')}</h3>
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          {INTEGRATION_KEYS.map((item) => (
            <div key={item.key} className="rounded-xl border border-white/10 bg-white/5 p-4">
              <div className={`mb-3 flex h-9 w-9 items-center justify-center rounded-xl ${
                item.tone === 'cyan'
                  ? 'bg-cyan-500/20 text-cyan-300'
                  : item.tone === 'violet'
                    ? 'bg-violet-500/20 text-violet-300'
                    : 'bg-emerald-500/20 text-emerald-300'
              }`}>
                <item.icon className="h-4 w-4" />
              </div>
              <p className="text-sm font-medium text-white">{t(`sdmPage.${item.key}`)}</p>
              <p className="mt-2 text-sm leading-6 text-gray-300">{t(`sdmPage.${item.descKey}`)}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="glass-card p-5">
        <div className="mb-4 flex items-center gap-2">
          <Layers className="h-4 w-4 text-cyan-400" />
          <h3 className="text-sm font-semibold text-white">{t('sdmPage.mapOverlays')}</h3>
        </div>
        <div className="mb-4 grid gap-2 md:grid-cols-4">
          <ToggleChip active={showHeatmap} onClick={() => setShowHeatmap((v) => !v)} icon={Flame} label={t('sdmPage.heatmap')} />
          <ToggleChip active={showDetections} onClick={() => setShowDetections((v) => !v)} icon={MapPin} label={t('sdmPage.detections')} />
          <ToggleChip active={showGbif} onClick={() => setShowGbif((v) => !v)} icon={Layers} label={`GBIF (${gbifPoints.length})`} />
          <ToggleChip active={showInat} onClick={() => setShowInat((v) => !v)} icon={Layers} label={`iNat (${inatPoints.length})`} />
        </div>
        <div id={mapId} className="h-80 overflow-hidden rounded-xl border border-white/10" style={{ background: '#101827' }} />
      </section>

      <section className="glass-card p-5">
        <div className="mb-4 flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-cyan-400" />
          <h3 className="text-sm font-semibold text-white">{t('sdmPage.priorityTitle')}</h3>
        </div>
        <div className="space-y-3">
          {PRIORITY_SITES.map((site) => (
            <div key={site.nameKey} className="flex flex-col gap-3 rounded-xl border border-white/10 bg-white/5 p-4 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex items-start gap-3">
                <MapPin className="mt-0.5 h-4 w-4 text-cyan-400" />
                <div>
                  <p className="text-sm font-medium text-white">{isZh ? site.nameZh : site.nameKey}</p>
                  <p className="mt-1 text-xs text-gray-500">{isZh ? site.reasonZh : site.reasonKey}</p>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <span className="text-xs text-gray-500">{site.lat} N, {site.lon} E</span>
                <span className={`rounded-full px-2.5 py-1 text-xs ${priorityTone[site.priority]}`}>
                  {t(`sdmPage.${site.priority}`)}
                </span>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}

function ToggleChip({ active, onClick, icon: Icon, label }) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center justify-center gap-2 rounded-lg border px-3 py-2 text-xs ${
        active ? 'border-emerald-500/30 bg-emerald-500/20 text-emerald-200' : 'border-white/10 bg-white/5 text-gray-400'
      }`}
    >
      <Icon className="h-3.5 w-3.5" />
      {label}
    </button>
  )
}

function SdmNote({ title, body }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-gray-400">{title}</p>
      <p className="mt-2 text-sm leading-6 text-gray-200">{body}</p>
    </div>
  )
}
