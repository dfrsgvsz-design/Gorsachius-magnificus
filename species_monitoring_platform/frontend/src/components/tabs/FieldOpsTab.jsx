import React, { useDeferredValue, useEffect, useMemo, useRef, useState } from 'react'
import {
  ChevronLeft,
  ClipboardList,
  Compass,
  FolderOpen,
  ListChecks,
  Loader2,
  MapPin,
  Camera,
  Clock,
  Play,
  Plus,
  RefreshCw,
  Route,
  Save,
  Square,
} from 'lucide-react'
import {
  FieldSurveyMap,
  RouteReportPanel,
  ProtocolExportPanel,
  VertebrateReviewPanel,
  TrackPanel,
  SyncPanel,
  MediaInboxPanel,
  MapToolsPanel,
  ObservationFormPanel,
  ProtocolSelectorPanel,
  ObservationListPanel,
} from '../fieldops'
import ComboField from '../fieldops/ComboField'
import {
  TAXA,
  DEFAULT_REMOTE_TILE_URL,
  DEFAULT_FIELD_TILE_PROXY_URL,
  TERRESTRIAL_VERTEBRATE_PROTOCOLS,
  COPY,
  pickLocale,
  buildProtocolCatalog,
  mergeTaxonomyCatalogEntries,
  findSpeciesMatch,
  createEmptyTransectSession,
  buildProtocolFieldState,
  normalizeProtocolFieldValues,
  matchesActiveSubmodule,
  matchesProtocolObservation,
  matchesProtocolTrack,
  getMatchingTaxonomyPackages,
  buildTaxonomyGateWarningMessage,
  buildTaxonomyMetricNote,
  buildTaxonomyGateBlockingMessage,
  localizeProtocol,
} from '../fieldops/protocolEngine'
import {
  EXPORT_JURISDICTIONS,
  toArray,
  downloadBlobFile,
  formatReportDescriptor,
  getSpeciesDisplayName,
  getSpeciesSecondaryName,
  splitObserverNames,
  getRequiredFieldLabels,
  buildPreviewEntries,
  formatPreviewValue,
  buildMaskPreview,
  formatPreviewKey,
  sortByRecent,
} from '../fieldops/fieldOpsUtils'
import useGeolocation from '../../hooks/useGeolocation'
import useTrackRecording from '../../hooks/useTrackRecording'
import useSyncEngine from '../../hooks/useSyncEngine'
import useProtocolSelection from '../../hooks/useProtocolSelection'
import { useTranslation } from 'react-i18next'
import { applyAttachmentContext } from '../../lib/attachmentContract'
import {
  createFieldSurveySite,
  createSurveyEvent,
  createSurveyExportJob,
  createOfflineMapPackage,
  createSurveyObservation,
  createSurveyProject,
  createSurveyTrack,
  exportSurveyRouteReport,
  getApiErrorMessage,
  getSurveyRouteSummary,
  getSurveyTaxonomyPackages,
  importSurveyRoute,
  resolveBackendAssetUrl,
  searchSurveyTaxonomy,
} from '../../lib/api'
import { StatusBanner } from '../common'
import { usePlatformConfig } from '../../lib/PlatformConfigContext'
import {
  attachmentListsMatch,
  buildTrackDraftForStart,
  createEmptyTrackDraft,
  normalizeAttachmentIds,
  normalizeTrackDraft,
  resolveDraftAttachments,
} from '../../lib/fieldOpsDrafts'
import {
  buildFeatureCollection,
  buildGpx,
  createDefaultProject,
  deriveSurveyTaxonomyPackageStatus,
  downloadTextFile,
  filterByProject,
  filterBySite,
  formatBytes,
  lineDistanceMeters,
  loadSurveyState,
  mergeStoredSurveyState,
  mergeSyncPull,
  normalizeJurisdiction,
  parseRouteFile,
  prefetchMapTiles,
  replaceEntity,
  saveSurveyState,
  serializeAttachment,
  snapObservationToRoutes,
  upsertLocalEntity,
} from '../../lib/surveyOffline'
import {
  CameraSource,
  ImpactStyle,
  capturePhotoAttachment,
  isNativeMobile,
  loadNativeSurveyState,
  pulseFeedback,
  requestNativeCurrentPosition,
  saveNativeSurveyState,
  startNativePositionWatch,
  stopNativePositionWatch,
} from '../../lib/mobileNative'
import { DEFAULT_SURVEY_MODULE_ID, FIELD_RELEASE_MODE } from '../../constants'


export default function FieldOpsTab({
  activeModule = DEFAULT_SURVEY_MODULE_ID,
  moduleMeta = null,
  onSelectModule = null,
}) {
  const { i18n } = useTranslation()
  const copy = COPY[pickLocale(i18n)]
  const locale = pickLocale(i18n)
  const platformConfig = usePlatformConfig()
  const nativeMobile = isNativeMobile()
  const [surveyState, setSurveyState] = useState(() => loadSurveyState())
  const [speciesCatalog, setSpeciesCatalog] = useState([])
  const [speciesSuggestions, setSpeciesSuggestions] = useState([])
  const [error, setError] = useState(null)
  const [downloadingTiles, setDownloadingTiles] = useState(false)
  const [importingRoute, setImportingRoute] = useState(false)
  const [serializingMedia, setSerializingMedia] = useState(false)
  const [audioCaptureStatus, setAudioCaptureStatus] = useState('idle')
  // GPS one-shot acquisition + listeners are encapsulated in `useGeolocation`.
  // `setCurrentPosition` is forwarded to `useTrackRecording` so live tracking
  // can replace the cached position with high-accuracy fixes.
  const { currentPosition, setCurrentPosition } = useGeolocation()
  const {
    liveTrack, trackStatus, trackInfo,
    transectSession, setTransectSession,
    trackDraftRef, watchRef,
    syncDraftIntoUi, setStoredTrackDraft,
    clearTrackWatch, pauseTrackDraft, handleTrackPoint,
  } = useTrackRecording({ setSurveyState, setCurrentPosition, setError })
  const audioRecorderRef = useRef(null)
  const audioStreamRef = useRef(null)
  const audioChunksRef = useRef([])
  const defaultProjectInitRef = useRef(false)
  const attachmentsRef = useRef([])
  const [projectForm, setProjectForm] = useState({ name: '', region: '' })
  const [siteForm, setSiteForm] = useState({ name: '', habitat_type: '', latitude: '', longitude: '' })
  const [transectForm, setTransectForm] = useState({ observer: '', weather: '', notes: '' })
  const [observationForm, setObservationForm] = useState({
    species_text: '',
    taxon_group: 'birds',
    count: 1,
    evidence_type: 'visual',
    confidence: 0.7,
    observer: '',
    behavior: '',
    habitat_notes: '',
    unknown_taxon: false,
    trace_only: false,
  })
  const [attachments, setAttachments] = useState([])
  const [nativeHydrationComplete, setNativeHydrationComplete] = useState(() => !nativeMobile)
  const [routeReport, setRouteReport] = useState(null)
  const [routeReportStatus, setRouteReportStatus] = useState('idle')
  const [routeReportError, setRouteReportError] = useState('')
  const [exportingRouteReportFormat, setExportingRouteReportFormat] = useState('')
  const [exportJurisdiction, setExportJurisdiction] = useState(() => (
    normalizeJurisdiction(loadSurveyState().activeJurisdiction, EXPORT_JURISDICTIONS[0].id)
  ))
  const [savingReviewEvent, setSavingReviewEvent] = useState(false)
  const [exportingVertebrateJurisdiction, setExportingVertebrateJurisdiction] = useState('')
  const [vertebrateExportResult, setVertebrateExportResult] = useState(null)
  const [surveyStep, setSurveyStep] = useState('setup')
  const [setupLevel, setSetupLevel] = useState('projects')
  const [surveyActive, setSurveyActive] = useState(false)
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const [showObservationSheet, setShowObservationSheet] = useState(false)
  const [liveTime, setLiveTime] = useState(() => new Date())
  const deferredSpeciesQuery = useDeferredValue(observationForm.species_text.trim())

  function replaceDraftAttachments(nextAttachments) {
    const normalizedAttachments = Array.isArray(nextAttachments) ? nextAttachments.filter(Boolean) : []
    const nextIds = normalizeAttachmentIds(normalizedAttachments.map((item) => item?.media_id))
    attachmentsRef.current = normalizedAttachments
    setAttachments(normalizedAttachments)
    setSurveyState((current) => ({ ...current, activeDraftAttachmentIds: nextIds }))
  }

  function appendDraftAttachments(nextAttachments) {
    const incomingAttachments = Array.isArray(nextAttachments) ? nextAttachments.filter(Boolean) : []
    if (incomingAttachments.length === 0) return
    const mergedAttachments = [...attachmentsRef.current, ...incomingAttachments]
    const nextIds = normalizeAttachmentIds(mergedAttachments.map((item) => item?.media_id))
    attachmentsRef.current = mergedAttachments
    setAttachments(mergedAttachments)
    setSurveyState((current) => ({
      ...current,
      mediaInbox: [...(current.mediaInbox || []), ...incomingAttachments],
      activeDraftAttachmentIds: nextIds,
    }))
  }

  useEffect(() => {
    saveSurveyState(surveyState)
    if (!nativeMobile || nativeHydrationComplete) {
      saveNativeSurveyState(surveyState).catch(() => {})
    }
  }, [nativeHydrationComplete, nativeMobile, surveyState])

  useEffect(() => {
    const restoredAttachments = resolveDraftAttachments(
      surveyState.mediaInbox,
      surveyState.activeDraftAttachmentIds,
    )
    const restoredIds = normalizeAttachmentIds(restoredAttachments.map((item) => item?.media_id))
    const currentIds = normalizeAttachmentIds(attachmentsRef.current.map((item) => item?.media_id))
    if (attachmentListsMatch(currentIds, restoredIds)) return
    attachmentsRef.current = restoredAttachments
    setAttachments(restoredAttachments)
  }, [surveyState.activeDraftAttachmentIds, surveyState.mediaInbox])

  useEffect(() => {
    if (!nativeMobile) {
      setNativeHydrationComplete(true)
      return undefined
    }
    let cancelled = false

    loadNativeSurveyState()
      .then((nativeState) => {
        if (!nativeState || cancelled) return
        setSurveyState((current) => mergeStoredSurveyState(current, nativeState))
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) {
          setNativeHydrationComplete(true)
        }
      })

    return () => {
      cancelled = true
    }
  }, [nativeMobile])


  useEffect(() => () => {
    if (audioRecorderRef.current && audioRecorderRef.current.state !== 'inactive') {
      audioRecorderRef.current.stop()
    }
    if (audioStreamRef.current) {
      audioStreamRef.current.getTracks().forEach((track) => track.stop())
      audioStreamRef.current = null
    }
  }, [])

  useEffect(() => () => {
    void clearTrackWatch()
  }, [])

  useEffect(() => {
    if (!surveyActive || !transectSession.started_at) return undefined
    const startMs = Date.parse(transectSession.started_at)
    if (!Number.isFinite(startMs)) return undefined
    const tick = () => {
      const s = Math.floor((Date.now() - startMs) / 1000)
      setElapsedSeconds(s >= 0 ? s : 0)
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [surveyActive, transectSession.started_at])

  useEffect(() => {
    if (surveyStep !== 'setup') return undefined
    const id = setInterval(() => setLiveTime(new Date()), 30000)
    return () => clearInterval(id)
  }, [surveyStep])

  useEffect(() => {
    const draft = normalizeTrackDraft(surveyState.activeTrackDraft)
    if (!draft) {
      if (!surveyState.activeTrackDraft && !watchRef.current) {
        syncDraftIntoUi(null)
      }
      return
    }
    syncDraftIntoUi(draft)
  }, [surveyState.activeTrackDraft])

  const activeTrackStatus = surveyState.activeTrackDraft?.tracking_status || ''

  useEffect(() => {
    const draft = normalizeTrackDraft(surveyState.activeTrackDraft)
    if (!draft || draft.tracking_status !== 'recording' || watchRef.current) return undefined

    let cancelled = false

    const handleWatchError = (error) => {
      if (cancelled) return
      void pauseTrackDraft(error?.message || 'Unable to record GPS positions.', draft)
    }

    const startWatch = async () => {
      try {
        if (nativeMobile) {
          const id = await startNativePositionWatch((position) => {
            if (!cancelled) handleTrackPoint(position)
          }, handleWatchError)
          if (cancelled) {
            await stopNativePositionWatch(id)
            return
          }
          watchRef.current = { kind: 'native', id }
          return
        }

        if (!navigator?.geolocation) {
          handleWatchError(new Error('Geolocation is not available in this browser.'))
          return
        }

        const id = navigator.geolocation.watchPosition(
          (position) => {
            if (cancelled) return
            handleTrackPoint({
              lat: position.coords.latitude,
              lon: position.coords.longitude,
              accuracy: position.coords.accuracy,
              timestamp: position.timestamp || Date.now(),
            })
          },
          handleWatchError,
          { enableHighAccuracy: true, maximumAge: 0, timeout: 10000 },
        )
        watchRef.current = { kind: 'web', id }
      } catch (error) {
        handleWatchError(error)
      }
    }

    void startWatch()

    return () => {
      cancelled = true
      void clearTrackWatch()
    }
  }, [nativeMobile, activeTrackStatus])

  const currentProjectId = surveyState.activeProjectId || surveyState.projects[0]?.project_id || ''
  const projectSites = useMemo(() => filterByProject(surveyState.sites, currentProjectId), [surveyState.sites, currentProjectId])
  const currentSiteId = surveyState.activeSiteId || projectSites[0]?.site_id || ''
  const currentProject = surveyState.projects.find((item) => item.project_id === currentProjectId) || null
  const currentSite = projectSites.find((item) => item.site_id === currentSiteId) || null
  const protocolCatalog = useMemo(() => buildProtocolCatalog(surveyState.protocols), [surveyState.protocols])
  const taxonomyCatalog = useMemo(
    () => mergeTaxonomyCatalogEntries(speciesCatalog, speciesSuggestions),
    [speciesCatalog, speciesSuggestions],
  )
  const {
    protocolState, setProtocolState, protocolDefinition, currentProgram,
    activeVertebrateSubmoduleId, activeVertebrateSubmodule, visibleProtocols,
    activeObservationTaxonGroups, activeTaxonomySearchGroup,
    handleSelectProgram, handleSelectProtocol, handleSelectVertebrateSubmodule,
    handleProtocolEventFieldChange, handleProtocolRecordFieldChange,
  } = useProtocolSelection({
    surveyState, setSurveyState,
    observationForm, setObservationForm,
    protocolCatalog,
    activeModule, onSelectModule,
    exportJurisdiction, setExportJurisdiction,
  })
  const {
    isOnline, loadingSync, bootstrapReady,
    handlePullSync, handlePushSync,
  } = useSyncEngine({
    surveyState, setSurveyState,
    protocolDefinition,
    activeVertebrateSubmoduleId,
    exportJurisdiction,
    currentProjectId,
    currentSiteId,
    setError,
  })
  const projectRoutes = useMemo(() => filterByProject(surveyState.routes, currentProjectId), [surveyState.routes, currentProjectId])
  const siteRoutes = useMemo(() => filterBySite(projectRoutes, currentSiteId), [projectRoutes, currentSiteId])
  const siteObservations = useMemo(() => filterBySite(filterByProject(surveyState.observations, currentProjectId), currentSiteId), [surveyState.observations, currentProjectId, currentSiteId])
  const siteTracks = useMemo(() => filterBySite(filterByProject(surveyState.tracks, currentProjectId), currentSiteId), [surveyState.tracks, currentProjectId, currentSiteId])
  const availableTaxaOptions = useMemo(
    () => (activeObservationTaxonGroups.length > 0 ? activeObservationTaxonGroups : TAXA),
    [activeObservationTaxonGroups],
  )
  const protocolObservations = useMemo(() => (
    siteObservations
      .filter((item) => matchesProtocolObservation(item, protocolDefinition, activeVertebrateSubmoduleId))
      .filter((item) => !item?.taxon_group || activeObservationTaxonGroups.length === 0 || activeObservationTaxonGroups.includes(item.taxon_group))
  ), [activeObservationTaxonGroups, activeVertebrateSubmoduleId, protocolDefinition, siteObservations])
  const protocolTracks = useMemo(() => (
    siteTracks.filter((item) => matchesProtocolTrack(item, protocolDefinition, activeVertebrateSubmoduleId))
  ), [siteTracks, protocolDefinition, activeVertebrateSubmoduleId])
  const selectedRoute = useMemo(() => {
    const explicitRoute = siteRoutes.find((item) => item.route_id === surveyState.activeRouteId) || null
    if (explicitRoute) return explicitRoute
    return protocolDefinition.requiresAsset ? (siteRoutes[0] || null) : null
  }, [protocolDefinition.requiresAsset, siteRoutes, surveyState.activeRouteId])
  const currentRouteId = selectedRoute?.route_id || ''
  const routeObservations = useMemo(() => (
    protocolObservations.filter((item) => {
      const linkedRouteId = item.route_id || item.snapped_route_id || ''
      const matchesRoute = currentRouteId ? linkedRouteId === currentRouteId : true
      return matchesRoute
    })
  ), [protocolObservations, currentRouteId])
  const routeTracks = useMemo(() => (
    protocolTracks.filter((item) => {
      const matchesRoute = currentRouteId ? item.route_id === currentRouteId : true
      return matchesRoute
    })
  ), [protocolTracks, currentRouteId])
  const activeMapPackages = useMemo(() => filterByProject(surveyState.mapPackages, currentProjectId), [surveyState.mapPackages, currentProjectId])
  const taxonomyGateByJurisdiction = useMemo(() => (
    Object.fromEntries(
      EXPORT_JURISDICTIONS.map((option) => [
        option.id,
        deriveSurveyTaxonomyPackageStatus(
          getMatchingTaxonomyPackages(
            surveyState.taxonomyPackages,
            protocolDefinition,
            option.id,
            activeVertebrateSubmoduleId,
          ),
        ),
      ]),
    )
  ), [surveyState.taxonomyPackages, protocolDefinition, activeVertebrateSubmoduleId])
  const activeTaxonomyPackageStatus = taxonomyGateByJurisdiction[exportJurisdiction] || deriveSurveyTaxonomyPackageStatus([])
  const activeTaxonomyPackage = activeTaxonomyPackageStatus.activePackage
  const activeJurisdictionLabel = EXPORT_JURISDICTIONS.find((item) => item.id === exportJurisdiction)?.label || exportJurisdiction
  const taxonomyGateWarningMessage = useMemo(
    () => buildTaxonomyGateWarningMessage(activeTaxonomyPackageStatus, locale),
    [activeTaxonomyPackageStatus, locale],
  )
  const taxonomyPackageNote = useMemo(
    () => buildTaxonomyMetricNote(activeTaxonomyPackageStatus, locale),
    [activeTaxonomyPackageStatus, locale],
  )
  useEffect(() => {
    if (!isOnline || !protocolDefinition.program || !protocolDefinition.id) return undefined
    let cancelled = false

    getSurveyTaxonomyPackages({
      jurisdiction: exportJurisdiction,
      program: protocolDefinition.program,
      protocol: protocolDefinition.id,
      submodule: protocolDefinition.program === 'terrestrial_vertebrates' ? activeVertebrateSubmoduleId : '',
    })
      .then((data) => {
        if (cancelled) return
        setSurveyState((current) => mergeSyncPull(current, {
          taxonomy_packages: toArray(data?.packages),
          active_program: protocolDefinition.program,
          active_protocol: protocolDefinition.id,
          active_vertebrate_submodule: protocolDefinition.program === 'terrestrial_vertebrates' ? activeVertebrateSubmoduleId : '',
          active_jurisdiction: exportJurisdiction,
          pulled_at: current.syncMeta?.lastPulledAt || '',
        }))
      })
      .catch(() => {})

    return () => {
      cancelled = true
    }
  }, [
    activeVertebrateSubmoduleId,
    exportJurisdiction,
    isOnline,
    protocolDefinition.id,
    protocolDefinition.program,
  ])
  const protocolEvents = useMemo(() => (
    toArray(surveyState.events)
      .filter((item) => item.project_id === currentProjectId)
      .filter((item) => !currentSiteId || item.site_id === currentSiteId)
      .filter((item) => (item.program || item.extra?.program || '') === protocolDefinition.program)
      .filter((item) => (item.protocol || item.extra?.protocol || '') === protocolDefinition.id)
      .filter((item) => matchesActiveSubmodule(item, protocolDefinition, activeVertebrateSubmoduleId))
      .filter((item) => !protocolDefinition.requiresAsset || !selectedRoute?.route_id || (item.route_id || '') === selectedRoute.route_id)
      .sort(sortByRecent)
  ), [surveyState.events, currentProjectId, currentSiteId, protocolDefinition.program, protocolDefinition.id, protocolDefinition.requiresAsset, selectedRoute?.route_id, activeVertebrateSubmoduleId])
  const jurisdictionEvents = useMemo(
    () => protocolEvents.filter((item) => (item.jurisdiction || item.extra?.jurisdiction || 'mainland_china') === exportJurisdiction),
    [protocolEvents, exportJurisdiction],
  )
  const latestProtocolEvent = useMemo(
    () => jurisdictionEvents.find((item) => item.event_id === surveyState.activeEventId) || jurisdictionEvents[0] || null,
    [jurisdictionEvents, surveyState.activeEventId],
  )
  const protocolExportJobs = useMemo(() => (
    toArray(surveyState.exportJobs)
      .filter((item) => item.project_id === currentProjectId)
      .filter((item) => !currentSiteId || !item.filters?.site_id || item.filters.site_id === currentSiteId)
      .filter((item) => !item.filters?.program || item.filters.program === protocolDefinition.program)
      .filter((item) => !item.filters?.protocol || item.filters.protocol === protocolDefinition.id)
      .filter((item) => matchesActiveSubmodule(item, protocolDefinition, activeVertebrateSubmoduleId))
      .sort(sortByRecent)
  ), [surveyState.exportJobs, currentProjectId, currentSiteId, protocolDefinition.program, protocolDefinition.id, activeVertebrateSubmoduleId])
  const latestProtocolExportJob = useMemo(
    () => protocolExportJobs.find((item) => item.jurisdiction === exportJurisdiction) || protocolExportJobs[0] || null,
    [protocolExportJobs, exportJurisdiction],
  )
  const latestTrack = routeTracks[0] || protocolTracks[0] || siteTracks[0] || null
  const transectEffortMinutes = useMemo(() => {
    if (!transectSession.started_at) return 0
    const endTime = transectSession.ended_at || new Date().toISOString()
    const started = Date.parse(transectSession.started_at)
    const ended = Date.parse(endTime)
    if (!Number.isFinite(started) || !Number.isFinite(ended) || ended < started) return 0
    return Math.round((ended - started) / 60000)
  }, [transectSession])
  const hasActiveTrackDraft = Boolean(normalizeTrackDraft(surveyState.activeTrackDraft))
  const selectedRouteLength = Math.round(selectedRoute?.length_m || lineDistanceMeters(selectedRoute?.geometry?.coordinates || []))
  const isZh = locale === 'zh'
  const mapCenter = useMemo(() => {
    if (currentPosition) return [currentPosition.lat, currentPosition.lon]
    if (currentSite?.latitude != null && currentSite?.longitude != null) return [currentSite.latitude, currentSite.longitude]
    return [
      platformConfig?.study_region?.center_lat || 24.7,
      platformConfig?.study_region?.center_lon || 110.5,
    ]
  }, [currentPosition, currentSite, platformConfig])

  const remoteTileUrl = platformConfig?.map?.tile_url || DEFAULT_REMOTE_TILE_URL
  const pilotTileProxyUrl = resolveBackendAssetUrl(platformConfig?.map?.tile_proxy_url || platformConfig?.map?.tile_proxy_path || DEFAULT_FIELD_TILE_PROXY_URL)
  const tileUrl = FIELD_RELEASE_MODE ? pilotTileProxyUrl : remoteTileUrl
  const tileAttribution = platformConfig?.map?.tile_attribution || '&copy; OpenStreetMap contributors'
  const isTerrestrialVertebrateProtocol = TERRESTRIAL_VERTEBRATE_PROTOCOLS.has(protocolDefinition.id)
  const normalizedEventFields = useMemo(
    () => normalizeProtocolFieldValues(protocolDefinition.eventFields, protocolState.event),
    [protocolDefinition.eventFields, protocolState.event],
  )
  const eventPayloadDraft = useMemo(() => {
    const payload = { ...normalizedEventFields }
    if (protocolDefinition.id.startsWith('bird_')) {
      payload.weather = transectForm.weather.trim()
    }
    return payload
  }, [normalizedEventFields, protocolDefinition.id, transectForm.weather])
  const eventValidationMissing = useMemo(() => {
    const missing = getRequiredFieldLabels(protocolDefinition.eventFields, protocolState.event)
    if (protocolDefinition.id.startsWith('bird_') && !transectForm.weather.trim()) {
      missing.push(copy.weather || 'Weather')
    }
    if (protocolDefinition.requiresAsset && !selectedRoute) {
      missing.push(protocolDefinition.assetLabel)
    }
    return missing
  }, [copy.weather, protocolDefinition.assetLabel, protocolDefinition.eventFields, protocolDefinition.id, protocolDefinition.requiresAsset, protocolState.event, selectedRoute, transectForm.weather])
  const recordValidationMissing = useMemo(() => {
    const missing = getRequiredFieldLabels(protocolDefinition.recordFields, protocolState.record)
    if (!observationForm.unknown_taxon && !observationForm.species_text.trim()) {
      missing.unshift('Species')
    }
    return missing
  }, [observationForm.species_text, observationForm.unknown_taxon, protocolDefinition.recordFields, protocolState.record])
  const currentMatchedSpecies = useMemo(
    () => findSpeciesMatch(taxonomyCatalog, observationForm.species_text),
    [observationForm.species_text, taxonomyCatalog],
  )
  useEffect(() => {
    if (!isOnline) return
    let cancelled = false

    searchSurveyTaxonomy({
      query: deferredSpeciesQuery,
      jurisdiction: exportJurisdiction,
      program: protocolDefinition.program,
      protocol: protocolDefinition.id,
      taxon_group: activeTaxonomySearchGroup,
      limit: deferredSpeciesQuery ? 80 : 250,
    })
      .then((data) => {
        if (cancelled) return
        const results = toArray(data?.results)
        setSpeciesSuggestions(results)
        if (results.length > 0) {
          setSpeciesCatalog((current) => mergeTaxonomyCatalogEntries(current, results))
        }
      })
      .catch(() => {
        if (cancelled) return
        setSpeciesSuggestions([])
      })

    return () => {
      cancelled = true
    }
  }, [
    activeTaxonomySearchGroup,
    deferredSpeciesQuery,
    exportJurisdiction,
    isOnline,
    protocolDefinition.id,
    protocolDefinition.program,
  ])
  const currentRecordMaskPreview = useMemo(
    () => buildMaskPreview({
      sensitivity: observationForm.trace_only ? 'review' : '',
      extra: {},
    }, currentMatchedSpecies, exportJurisdiction),
    [currentMatchedSpecies, exportJurisdiction, observationForm.trace_only],
  )
  const currentRecordPayloadDraft = useMemo(
    () => buildObservationRecordPayload({
      matched: currentMatchedSpecies,
      observedAt: latestProtocolEvent?.started_at || new Date().toISOString(),
      linkedEventId: latestProtocolEvent?.event_id || '',
    }),
    [
      currentMatchedSpecies,
      latestProtocolEvent?.event_id,
      latestProtocolEvent?.started_at,
      observationForm.behavior,
      observationForm.count,
      observationForm.evidence_type,
      protocolDefinition.id,
      protocolDefinition.recordFields,
      protocolState.record,
    ],
  )
  const recentVertebrateRecordPreviews = useMemo(() => (
    routeObservations
      .slice(0, 6)
      .map((record) => {
        const matched = findSpeciesMatch(
          taxonomyCatalog,
          record.scientific_name || record.chinese_name || record.english_name || '',
        )
        const recordPayload = record.record_payload
          || record.extra?.record_payload
          || {
            ...normalizeProtocolFieldValues(protocolDefinition.recordFields, record.extra?.record_fields || {}),
            count: record.count,
            taxon_id: record.taxon_id || matched?.internal_taxon_id || matched?.taxon_id || '',
            observation_time: record.observed_at || '',
            evidence_type: record.evidence_type || '',
          }
        return {
          record,
          matched,
          recordPayload,
          maskPreview: buildMaskPreview(record, matched, exportJurisdiction),
        }
      })
  ), [exportJurisdiction, protocolDefinition.recordFields, routeObservations, taxonomyCatalog])
  const maskedPreviewCount = useMemo(
    () => recentVertebrateRecordPreviews.filter((item) => item.maskPreview.masked).length,
    [recentVertebrateRecordPreviews],
  )

  useEffect(() => {
    if (!platformConfig?._loaded || surveyState.projects.length > 0 || !bootstrapReady || defaultProjectInitRef.current) return

    defaultProjectInitRef.current = true
    const defaultProject = createDefaultProject(platformConfig)

    if (isOnline) {
      createSurveyProject(defaultProject)
        .then((response) => {
          setSurveyState((current) => replaceEntity(current, 'project', response.project, { select: true }))
        })
        .catch(() => {
          setSurveyState((current) => upsertLocalEntity(current, 'project', defaultProject))
        })
      return
    }

    setSurveyState((current) => upsertLocalEntity(current, 'project', defaultProject))
  }, [bootstrapReady, isOnline, platformConfig, surveyState.projects.length])

  useEffect(() => {
    if (siteRoutes.length === 0) {
      if (surveyState.activeRouteId) {
        setSurveyState((current) => ({ ...current, activeRouteId: '' }))
      }
      return
    }
    if (surveyState.activeRouteId) {
      if (siteRoutes.some((item) => item.route_id === surveyState.activeRouteId)) return
      setSurveyState((current) => ({ ...current, activeRouteId: '' }))
      return
    }
    if (!protocolDefinition.requiresAsset) return
    setSurveyState((current) => ({ ...current, activeRouteId: siteRoutes[0]?.route_id || '' }))
  }, [protocolDefinition.requiresAsset, siteRoutes, surveyState.activeRouteId])

  useEffect(() => {
    if (!latestProtocolEvent?.event_id) {
      if (surveyState.activeEventId) {
        setSurveyState((current) => ({ ...current, activeEventId: '' }))
      }
      return
    }
    if (surveyState.activeEventId === latestProtocolEvent.event_id) return
    setSurveyState((current) => ({ ...current, activeEventId: latestProtocolEvent.event_id }))
  }, [latestProtocolEvent?.event_id, surveyState.activeEventId])

  useEffect(() => {
    setTransectSession((current) => {
      if (!current.started_at) return current
      if (!selectedRoute || current.route_id === selectedRoute.route_id) return current
      return createEmptyTransectSession(transectForm.observer || observationForm.observer || '')
    })
  }, [selectedRoute, transectForm.observer, observationForm.observer])

  useEffect(() => {
    let cancelled = false

    if (!selectedRoute?.route_id) {
      setRouteReport(null)
      setRouteReportStatus('idle')
      setRouteReportError('')
      return undefined
    }

    if (!isOnline) {
      setRouteReport(null)
      setRouteReportStatus('offline')
      setRouteReportError('')
      return undefined
    }

    setRouteReportStatus('loading')
    setRouteReportError('')

    getSurveyRouteSummary(selectedRoute.route_id)
      .then((data) => {
        if (cancelled) return
        setRouteReport(data?.summary || null)
        setRouteReportStatus('ready')
      })
      .catch((err) => {
        if (cancelled) return
        setRouteReport(null)
        setRouteReportStatus('error')
        setRouteReportError(getApiErrorMessage(err, 'Unable to load the route or station report.'))
      })

    return () => {
      cancelled = true
    }
  }, [isOnline, selectedRoute?.route_id])

  useEffect(() => {
    setVertebrateExportResult(null)
  }, [protocolDefinition.id, exportJurisdiction, selectedRoute?.route_id])

  function handleSelectRoute(routeId) {
    setSurveyState((current) => ({ ...current, activeRouteId: routeId }))
    setTransectSession((current) => {
      if (!current.started_at) return { ...current, route_id: routeId }
      if (current.route_id === routeId) return current
      return createEmptyTransectSession(transectForm.observer || observationForm.observer || '')
    })
  }

  async function handleImportRoute(event) {
    const file = event.target.files?.[0]
    if (!file || !currentProjectId) return
    setImportingRoute(true)
    setError(null)
    try {
      let routePayload
      if (isOnline) {
        const response = await importSurveyRoute(file, {
          projectId: currentProjectId,
          siteId: currentSiteId,
          name: file.name.replace(/\.[^.]+$/, ''),
          routeType: protocolDefinition.requiresAsset ? 'transect' : 'station',
        })
        routePayload = {
          ...response.route,
          extra: {
            ...(response.route?.extra || {}),
            ...buildProtocolExtra('event'),
          },
          sync_state: 'synced',
          server_updated_at: response.route.updated_at,
        }
        setSurveyState((current) => ({
          ...current,
          activeRouteId: routePayload.route_id,
          routes: [...current.routes.filter((item) => item.route_id !== routePayload.route_id), routePayload].sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || '')),
        }))
      } else {
        const parsed = await parseRouteFile(file)
        setSurveyState((current) => upsertLocalEntity(current, 'route', {
          project_id: currentProjectId,
          site_id: currentSiteId,
          route_type: protocolDefinition.requiresAsset ? 'transect' : 'station',
          ...parsed,
          extra: buildProtocolExtra('event'),
        }, { operation: 'upsert', select: true }))
      }
    } catch (err) {
      setError(getApiErrorMessage(err, isZh ? '无法导入所选路线文件。' : 'Unable to import the selected route file.'))
    } finally {
      event.target.value = ''
      setImportingRoute(false)
    }
  }

  async function handleAddAttachments(event) {
    const files = Array.from(event.target.files || [])
    if (files.length === 0) return
    setSerializingMedia(true)
    setError(null)
    try {
      const serialized = []
      for (const file of files) {
        serialized.push(await serializeAttachment(file))
      }
      appendDraftAttachments(serialized)
    } catch (err) {
      setError(getApiErrorMessage(err, isZh ? '无法在本地存储附件。' : 'Unable to store attachments locally.'))
    } finally {
      event.target.value = ''
      setSerializingMedia(false)
    }
  }

  async function handleCapturePhoto() {
    if (!nativeMobile) return
    setSerializingMedia(true)
    setError(null)
    try {
      const attachment = await capturePhotoAttachment(CameraSource.Camera)
      if (!attachment) return
      await pulseFeedback(ImpactStyle.Light)
      appendDraftAttachments([attachment])
    } catch (err) {
      setError(getApiErrorMessage(err, isZh ? '无法在此设备拍摄照片。' : 'Unable to capture a field photo on this device.'))
    } finally {
      setSerializingMedia(false)
    }
  }

  async function handleStartAudioCapture() {
    if (typeof window === 'undefined' || !navigator?.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setError(isZh ? '此浏览器或设备不支持录音功能。' : 'Audio recording is not supported in this browser or device.')
      return
    }
    if (audioCaptureStatus === 'recording') return
    setSerializingMedia(true)
    setError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mimeType = MediaRecorder.isTypeSupported?.('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : ''
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
      audioChunksRef.current = []
      audioStreamRef.current = stream
      audioRecorderRef.current = recorder
      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) audioChunksRef.current.push(event.data)
      }
      recorder.onstop = async () => {
        try {
          const blob = new Blob(audioChunksRef.current, {
            type: recorder.mimeType || 'audio/webm',
          })
          if (blob.size > 0) {
            const extension = blob.type.includes('ogg') ? 'ogg' : 'webm'
            const file = new File([blob], `field-audio-${Date.now()}.${extension}`, {
              type: blob.type || 'audio/webm',
            })
            const attachment = await serializeAttachment(file)
            appendDraftAttachments([attachment])
            setObservationForm((current) => ({ ...current, evidence_type: 'audio' }))
            await pulseFeedback(ImpactStyle.Light)
          }
        } catch (err) {
          setError(getApiErrorMessage(err, isZh ? '无法保存录制的音频证据。' : 'Unable to save the recorded audio evidence.'))
        } finally {
          if (audioStreamRef.current) {
            audioStreamRef.current.getTracks().forEach((track) => track.stop())
            audioStreamRef.current = null
          }
          audioRecorderRef.current = null
          audioChunksRef.current = []
          setAudioCaptureStatus('idle')
          setSerializingMedia(false)
        }
      }
      recorder.start()
      setObservationForm((current) => ({ ...current, evidence_type: 'audio' }))
      setAudioCaptureStatus('recording')
      await pulseFeedback(ImpactStyle.Light)
    } catch (err) {
      setSerializingMedia(false)
      setAudioCaptureStatus('idle')
      setError(getApiErrorMessage(err, isZh ? '无法在此设备启动录音。' : 'Unable to start audio recording on this device.'))
    }
  }

  async function handleStopAudioCapture() {
    if (!audioRecorderRef.current || audioRecorderRef.current.state === 'inactive') return
    try {
      audioRecorderRef.current.stop()
    } catch (err) {
      setSerializingMedia(false)
      setAudioCaptureStatus('idle')
      setError(getApiErrorMessage(err, isZh ? '无法正常停止录音。' : 'Unable to stop audio recording cleanly.'))
    }
  }

  async function useCurrentGps() {
    if (nativeMobile) {
      try {
        const position = await requestNativeCurrentPosition()
        if (!position) return
        setCurrentPosition(position)
        setSiteForm((current) => ({
          ...current,
          latitude: String(position.lat.toFixed(6)),
          longitude: String(position.lon.toFixed(6)),
        }))
        await pulseFeedback(ImpactStyle.Light)
      } catch (err) {
        setError(getApiErrorMessage(err, isZh ? '当前无法使用设备 GPS。' : 'Unable to use the device GPS right now.'))
      }
      return
    }

    if (!currentPosition) return
    setSiteForm((current) => ({
      ...current,
      latitude: String(currentPosition.lat.toFixed(6)),
      longitude: String(currentPosition.lon.toFixed(6)),
    }))
  }

  function buildEventGeometry() {
    if (selectedRoute?.geometry) return selectedRoute.geometry
    if (currentSite?.latitude != null && currentSite?.longitude != null) {
      return { type: 'Point', coordinates: [currentSite.longitude, currentSite.latitude] }
    }
    if (currentPosition?.lat != null && currentPosition?.lon != null) {
      return { type: 'Point', coordinates: [currentPosition.lon, currentPosition.lat] }
    }
    return null
  }

  function buildSamplingEventRequest(eventId = '') {
    const startedAt = transectSession.started_at || new Date().toISOString()
    const endedAt = transectSession.ended_at || ''
    const observers = splitObserverNames(transectForm.observer, observationForm.observer)
    const activeSubmodule = currentProgram === 'terrestrial_vertebrates'
      ? activeVertebrateSubmoduleId
      : (protocolDefinition.defaultTaxonGroup || '')
    const effortMetrics = {
      observer_count: Number(protocolState.event.observer_count || 0) || observers.length || 0,
      observation_count: protocolObservations.length,
      track_count: protocolTracks.length,
      duration_min: transectEffortMinutes || Number(protocolState.event.duration_min || protocolState.event.point_duration_min || 0) || 0,
    }
    if (selectedRouteLength > 0) {
      effortMetrics.route_length_m = selectedRouteLength
    }
    if (protocolDefinition.supportsTrack && trackInfo.distance_m > 0) {
      effortMetrics.distance_walked_m = Math.round(trackInfo.distance_m)
    }
    return {
      event_id: eventId || surveyState.activeEventId || `event-${Date.now()}`,
      project_id: currentProjectId,
      site_id: currentSiteId,
      route_id: selectedRoute?.route_id || '',
      design_asset_id: surveyState.activeDesignAssetId || '',
      program: protocolDefinition.program,
      submodule: activeSubmodule,
      protocol: protocolDefinition.id,
      jurisdiction: exportJurisdiction,
      started_at: startedAt,
      ended_at: endedAt,
      geometry: buildEventGeometry(),
      weather: {
        summary: transectForm.weather.trim(),
      },
      effort_metrics: effortMetrics,
      event_payload: eventPayloadDraft,
      observers,
      team: [],
      notes: transectForm.notes.trim(),
      sync_state: isOnline ? 'synced' : 'queued',
      extra: {
        ...buildProtocolExtra('event', { eventPayload: eventPayloadDraft }),
        route_id: selectedRoute?.route_id || '',
      },
    }
  }

  function buildObservationRecordPayload({ matched, observedAt, linkedEventId = '' }) {
    const payload = normalizeProtocolFieldValues(protocolDefinition.recordFields, protocolState.record)
    if (matched?.internal_taxon_id || matched?.taxon_id || matched?.species_id) {
      payload.taxon_id = matched.internal_taxon_id || matched.taxon_id || matched.species_id
    }
    payload.count = Number(observationForm.count || 1)
    payload.observation_time = observedAt
    if (protocolDefinition.id === 'herp_infrared_camera') {
      payload.evidence_type = observationForm.evidence_type
    } else if (!payload.detection_type) {
      payload.detection_type = observationForm.evidence_type
    }
    if (!payload.behavior && observationForm.behavior.trim()) {
      payload.behavior = observationForm.behavior.trim()
    }
    if (linkedEventId) {
      payload.event_id = linkedEventId
    }
    if (currentProgram === 'terrestrial_vertebrates' && activeVertebrateSubmoduleId) {
      payload.submodule = activeVertebrateSubmoduleId
    }
    return payload
  }

  function buildObservationMediaPayload(linkedEventId = '') {
    const activeSubmodule = currentProgram === 'terrestrial_vertebrates'
      ? activeVertebrateSubmoduleId
      : (protocolDefinition.defaultTaxonGroup || '')
    const attachmentIds = normalizeAttachmentIds(
      attachments.map((item) => item?.attachment_id || item?.media_id),
    )
    return applyAttachmentContext(attachments, attachmentIds, {
      owner_type: linkedEventId ? 'event' : 'draft',
      owner_id: linkedEventId || surveyState.activeDesignAssetId || selectedRoute?.route_id || currentSiteId || currentProjectId || '',
      event_id: linkedEventId,
      sync_state: 'local_only',
    }).map((item) => ({
      ...item,
      program: protocolDefinition.program,
      submodule: activeSubmodule,
      protocol: protocolDefinition.id,
      jurisdiction: exportJurisdiction,
    }))
  }

  function buildProtocolExtra(kind = 'event', options = {}) {
    const eventPayload = options.eventPayload || eventPayloadDraft
    const activeSubmodule = currentProgram === 'terrestrial_vertebrates'
      ? activeVertebrateSubmoduleId
      : (protocolDefinition.defaultTaxonGroup || '')
    const extra = {
      program: protocolDefinition.program,
      submodule: activeSubmodule,
      protocol: protocolDefinition.id,
      protocol_label: protocolDefinition.label,
      asset_label: protocolDefinition.assetLabel,
      jurisdiction: exportJurisdiction,
      event_fields: eventPayload,
      event_payload: eventPayload,
    }
    if (kind === 'record') {
      extra.record_fields = options.recordPayload || normalizeProtocolFieldValues(protocolDefinition.recordFields, protocolState.record)
      extra.record_payload = options.recordPayload || normalizeProtocolFieldValues(protocolDefinition.recordFields, protocolState.record)
      if (options.eventId) {
        extra.event_id = options.eventId
      }
    }
    return extra
  }

  async function saveReviewEventOnlineAware({ quiet = false } = {}) {
    if (!currentProjectId) return null
    if (eventValidationMissing.length > 0) {
      setError(isZh
        ? `请先完成以下 ${protocolDefinition.label} 事件字段再保存或导出：${eventValidationMissing.join('、')}`
        : `Complete these ${protocolDefinition.label} event fields before saving or exporting: ${eventValidationMissing.join(', ')}`)
      return null
    }
    const payload = buildSamplingEventRequest()
    const latestComparable = latestProtocolEvent
      ? JSON.stringify({
        protocol: latestProtocolEvent.protocol,
        submodule: latestProtocolEvent.submodule || latestProtocolEvent.extra?.submodule || '',
        jurisdiction: latestProtocolEvent.jurisdiction,
        route_id: latestProtocolEvent.route_id,
        event_payload: latestProtocolEvent.event_payload || latestProtocolEvent.extra?.event_payload || {},
        notes: latestProtocolEvent.notes || '',
      })
      : ''
    const draftComparable = JSON.stringify({
      protocol: payload.protocol,
      submodule: payload.submodule || '',
      jurisdiction: payload.jurisdiction,
      route_id: payload.route_id,
      event_payload: payload.event_payload,
      notes: payload.notes,
    })
    if (latestProtocolEvent && latestComparable === draftComparable) {
      return latestProtocolEvent
    }
    setSavingReviewEvent(true)
    setError(null)
    try {
      if (isOnline) {
        const response = await createSurveyEvent(payload)
        setSurveyState((current) => replaceEntity(current, 'event', response.event, { select: true }))
        if (!quiet) {
          setVertebrateExportResult((current) => ({
            ...(current || {}),
            latestEvent: response.event,
          }))
        }
        return response.event
      }
      setSurveyState((current) => upsertLocalEntity(current, 'event', payload, { select: true }))
      if (!quiet) {
        setVertebrateExportResult((current) => ({
          ...(current || {}),
          latestEvent: payload,
        }))
      }
      return payload
    } catch (err) {
      setSurveyState((current) => upsertLocalEntity(current, 'event', payload, { select: true }))
      setError(getApiErrorMessage(err, isZh ? '事件已保存到本地并加入同步队列。' : 'Event saved locally and queued for sync.'))
      return payload
    } finally {
      setSavingReviewEvent(false)
    }
  }

  async function handleCreateProtocolExport(jurisdiction, { requireMaskPreview = false } = {}) {
    if (!isOnline || !currentProjectId) return null
    if (protocolObservations.length === 0) {
      setError(isZh
        ? `请先保存至少一条 ${protocolDefinition.label} 观测记录再导出。`
        : `Save at least one ${protocolDefinition.label.toLowerCase()} observation before exporting.`)
      return null
    }
    const exportTaxonomyPackageStatus = taxonomyGateByJurisdiction[jurisdiction] || deriveSurveyTaxonomyPackageStatus([])
    const exportJurisdictionLabel = EXPORT_JURISDICTIONS.find((item) => item.id === jurisdiction)?.label || jurisdiction
    if (exportTaxonomyPackageStatus.isBlocked) {
      setError(buildTaxonomyGateBlockingMessage(exportTaxonomyPackageStatus, protocolDefinition, exportJurisdictionLabel, locale))
      return null
    }
    setExportingVertebrateJurisdiction(jurisdiction)
    setError(null)
    try {
      const eventRecord = await saveReviewEventOnlineAware({ quiet: requireMaskPreview })
      const response = await createSurveyExportJob(jurisdiction, {
        project_id: currentProjectId,
        site_id: currentSiteId,
        program: protocolDefinition.program,
        submodule: protocolDefinition.program === 'terrestrial_vertebrates' ? activeVertebrateSubmoduleId : '',
        protocol: protocolDefinition.id,
        event_id: eventRecord?.event_id || latestProtocolEvent?.event_id || '',
        format: 'csv',
        extra: {
          route_id: selectedRoute?.route_id || '',
          design_asset_id: surveyState.activeDesignAssetId || '',
          submodule: protocolDefinition.program === 'terrestrial_vertebrates' ? activeVertebrateSubmoduleId : '',
        },
      })
      const exportJob = response.export_job || response
      setSurveyState((current) => replaceEntity(current, 'export_job', exportJob))
      const files = toArray(exportJob?.bundle?.files)
      files.forEach((file) => {
        if (!file?.content) return
        downloadTextFile(
          file.filename || `${protocolDefinition.id}-${file.output_id || 'export'}.csv`,
          file.content,
          file.media_type || 'text/csv;charset=utf-8',
        )
      })
      return {
        eventRecord,
        exportJob,
        summary: response.summary || exportJob.summary || {},
      }
    } catch (err) {
      setError(getApiErrorMessage(err, isZh
        ? `无法导出 ${jurisdiction.replace(/_/g, ' ')} ${protocolDefinition.label} 数据包。`
        : `Unable to export the ${jurisdiction.replace(/_/g, ' ')} ${protocolDefinition.label.toLowerCase()} bundle.`))
      return null
    } finally {
      setExportingVertebrateJurisdiction('')
    }
  }

  async function handleCreateVertebrateExport(jurisdiction) {
    if (!isTerrestrialVertebrateProtocol) return
    const result = await handleCreateProtocolExport(jurisdiction, { requireMaskPreview: true })
    if (result) {
      setVertebrateExportResult({
        jurisdiction,
        exportJob: result.exportJob,
        summary: result.summary,
      })
    }
  }

  function handleStartTrack() {
    if (!protocolDefinition.supportsTrack) {
      setError(isZh
      ? `${protocolDefinition.label} 使用站点/样方工作流，实时轨迹记录已禁用。`
      : `${protocolDefinition.label} uses a station or plot workflow, so live track recording is disabled.`)
      return
    }
    if (!nativeMobile && !navigator?.geolocation) {
      setError(isZh ? '此浏览器不支持地理定位功能。' : 'Geolocation is not available in this browser.')
      return
    }
    if (watchRef.current) return
    const nextDraft = buildTrackDraftForStart({
      existingDraft: surveyState.activeTrackDraft,
      selectedRoute: selectedRoute || null,
      observer: transectForm.observer,
      weather: transectForm.weather,
      notes: transectForm.notes,
      extra: buildProtocolExtra('event'),
      startedAt: new Date().toISOString(),
    })

    setStoredTrackDraft(nextDraft)
  }

  async function submitProjectOnlineAware() {
    const name = projectForm.name.trim() || `${platformConfig?.target_species?.common_name_zh || '外业'}项目`
    const payload = {
      name,
      region: projectForm.region.trim() || platformConfig?.study_region?.name_zh || platformConfig?.study_region?.name || '',
      team_members: [],
      target_taxa: TAXA,
      notes: '',
    }
    try {
      if (isOnline) {
        const response = await createSurveyProject(payload)
        setSurveyState((current) => replaceEntity(current, 'project', response.project, { select: true }))
      } else {
        setSurveyState((current) => upsertLocalEntity(current, 'project', payload))
      }
      setProjectForm({ name: '', region: '' })
    } catch (err) {
      setSurveyState((current) => upsertLocalEntity(current, 'project', payload))
      setProjectForm({ name: '', region: '' })
      setError(getApiErrorMessage(err, isZh ? '项目已保存到本地并加入同步队列。' : 'Project saved locally and queued for sync.'))
    }
  }

  async function saveSiteOnlineAware() {
    if (!currentProjectId) return
    const latitude = siteForm.latitude ? Number(siteForm.latitude) : currentPosition?.lat
    const longitude = siteForm.longitude ? Number(siteForm.longitude) : currentPosition?.lon
    const payload = {
      project_id: currentProjectId,
      name: siteForm.name.trim() || `Site ${projectSites.length + 1}`,
      habitat_type: siteForm.habitat_type.trim(),
      latitude,
      longitude,
      admin_region: currentProject?.region || '',
    }
    try {
      if (isOnline) {
        const response = await createFieldSurveySite(payload)
        setSurveyState((current) => replaceEntity(current, 'site', response.site, { select: true }))
      } else {
        setSurveyState((current) => upsertLocalEntity(current, 'site', payload))
      }
      setSiteForm({ name: '', habitat_type: '', latitude: '', longitude: '' })
    } catch (err) {
      setSurveyState((current) => upsertLocalEntity(current, 'site', payload))
      setSiteForm({ name: '', habitat_type: '', latitude: '', longitude: '' })
      setError(getApiErrorMessage(err, isZh ? '站点已保存到本地并加入同步队列。' : 'Site saved locally and queued for sync.'))
    }
  }

  async function preloadTilesOnlineAware() {
    setDownloadingTiles(true)
    setError(null)
    try {
      // Prefer the configured study region; fall back to a buffer around the
      // current map centre so a crew can pre-cache tiles before any project
      // exists (e.g. on first device launch).
      const bbox = platformConfig?.study_region?.bounding_box || {
        min_lat: mapCenter[0] - 0.2,
        max_lat: mapCenter[0] + 0.2,
        min_lon: mapCenter[1] - 0.2,
        max_lon: mapCenter[1] + 0.2,
      }
      const minZoom = 8
      const maxZoom = Math.min(14, platformConfig?.map?.max_zoom || 14)
      const cached = await prefetchMapTiles({
        tileUrl,
        bbox,
        minZoom,
        maxZoom,
        cacheKey: currentProjectId || 'default',
      })
      // Only attempt to register the package server-side once a project exists.
      // Without `project_id`, the survey API will reject the package, but the
      // tiles are already in the shared service-worker cache and remain useful.
      if (!currentProjectId) {
        return
      }
      const payload = {
        project_id: currentProjectId,
        name: `${currentProject?.name || 'Survey'} tiles`,
        bbox,
        min_zoom: minZoom,
        max_zoom: maxZoom,
        tile_url: tileUrl,
        tile_count_estimate: cached.total,
        storage_bytes_estimate: cached.downloaded * 18000,
        status: cached.downloaded > 0 ? 'cached' : 'planned',
        extra: {
          capped: cached.capped,
          downloaded_tiles: cached.downloaded,
          failed_tiles: cached.failed || 0,
        },
      }
      if (isOnline) {
        try {
          const response = await createOfflineMapPackage(payload)
          setSurveyState((current) => replaceEntity(current, 'map_package', response.package))
        } catch (err) {
          setSurveyState((current) => upsertLocalEntity(current, 'map_package', payload))
          setError(getApiErrorMessage(err, isZh ? '离线地图包已保存到本地并加入同步队列。' : 'Offline map package saved locally and queued for sync.'))
        }
      } else {
        setSurveyState((current) => upsertLocalEntity(current, 'map_package', payload))
      }
    } catch (err) {
      setError(getApiErrorMessage(err, isZh ? '无法缓存该区域的离线地图瓦片。' : 'Unable to cache offline tiles for this area.'))
    } finally {
      setDownloadingTiles(false)
    }
  }

  async function saveObservationOnlineAware() {
    if (!currentProjectId || (protocolDefinition.requiresAsset && !selectedRoute)) return
    if (recordValidationMissing.length > 0) {
      setError(isZh
        ? `请先完成以下 ${protocolDefinition.label} 记录字段再保存：${recordValidationMissing.join('、')}`
        : `Complete these ${protocolDefinition.label} record fields before saving: ${recordValidationMissing.join(', ')}`)
      return false
    }
    const eventRecord = await saveReviewEventOnlineAware({ quiet: true })
    if (!eventRecord?.event_id) return false
    const matched = findSpeciesMatch(taxonomyCatalog, observationForm.species_text)
    const observedAt = new Date().toISOString()
    const linkedEventId = eventRecord.event_id
    const recordPayload = buildObservationRecordPayload({ matched, observedAt, linkedEventId })
    const latitude = currentPosition?.lat ?? currentSite?.latitude ?? null
    const longitude = currentPosition?.lon ?? currentSite?.longitude ?? null
    const snapped = latitude != null && longitude != null
      ? snapObservationToRoutes([longitude, latitude], siteRoutes)
      : { snapped_route_id: '', snapped_distance_m: 0 }
    const payload = {
      project_id: currentProjectId,
      site_id: currentSiteId,
      route_id: selectedRoute?.route_id || snapped.snapped_route_id || '',
      event_id: linkedEventId,
      program: protocolDefinition.program,
      submodule: currentProgram === 'terrestrial_vertebrates' ? activeVertebrateSubmoduleId : (protocolDefinition.defaultTaxonGroup || ''),
      protocol: protocolDefinition.id,
      jurisdiction: exportJurisdiction,
      scientific_name: matched?.scientific || matched?.scientific_name || (observationForm.unknown_taxon ? '' : observationForm.species_text.trim()),
      chinese_name: matched?.chinese || matched?.chinese_name || '',
      english_name: matched?.english || matched?.english_name || '',
      taxon_group: observationForm.taxon_group,
      count: Number(observationForm.count || 1),
      evidence_type: observationForm.evidence_type,
      behavior: observationForm.behavior.trim(),
      habitat_notes: observationForm.habitat_notes.trim(),
      confidence: Number(observationForm.confidence || 0.5),
      observer: observationForm.observer.trim(),
      unknown_taxon: observationForm.unknown_taxon,
      trace_only: observationForm.trace_only,
      latitude,
      longitude,
      geometry: latitude != null && longitude != null ? { type: 'Point', coordinates: [longitude, latitude] } : null,
      media: buildObservationMediaPayload(linkedEventId),
      observed_at: observedAt,
      snapped_route_id: snapped.snapped_route_id || selectedRoute?.route_id || '',
      snapped_distance_m: snapped.snapped_distance_m,
      transect_observer: transectSession.observer || transectForm.observer.trim(),
      transect_weather: transectSession.weather || transectForm.weather.trim(),
      transect_notes: transectSession.notes || transectForm.notes.trim(),
      transect_started_at: transectSession.started_at || '',
      ai_suggestion: matched ? {
        scientific_name: matched.scientific || matched.scientific_name || '',
        chinese_name: matched.chinese || matched.chinese_name || '',
        english_name: matched.english || matched.english_name || '',
      } : {},
      record_payload: recordPayload,
      extra: buildProtocolExtra('record', { recordPayload, eventId: linkedEventId }),
    }
    const resetForm = () => {
      setObservationForm({
        species_text: '',
        taxon_group: observationForm.taxon_group,
        count: 1,
        evidence_type: observationForm.evidence_type,
        confidence: observationForm.confidence,
        observer: observationForm.observer,
        behavior: '',
        habitat_notes: '',
        unknown_taxon: false,
        trace_only: false,
      })
      setProtocolState((current) => ({
        ...current,
        record: buildProtocolFieldState(protocolDefinition.recordFields),
      }))
      replaceDraftAttachments([])
    }
    try {
      if (isOnline) {
        const response = await createSurveyObservation(payload)
        setSurveyState((current) => replaceEntity(current, 'observation', response.observation))
      } else {
        setSurveyState((current) => upsertLocalEntity(current, 'observation', payload))
      }
      resetForm()
      return true
    } catch (err) {
      setSurveyState((current) => upsertLocalEntity(current, 'observation', payload))
      resetForm()
      setError(getApiErrorMessage(err, isZh ? '观测记录已保存到本地并加入同步队列。' : 'Observation saved locally and queued for sync.'))
      return true
    }
  }

  async function stopTrackOnlineAware() {
    await clearTrackWatch()
    const draft = normalizeTrackDraft(trackDraftRef.current)
    if (!draft) {
      setSurveyState((current) => ({ ...current, activeTrackDraft: null }))
      syncDraftIntoUi(null)
      return
    }
    const endedAt = new Date().toISOString()
    if (draft.points.length > 1 && currentProjectId) {
      const eventRecord = await saveReviewEventOnlineAware({ quiet: true })
      if (!eventRecord?.event_id) return
      const payload = {
        project_id: currentProjectId,
        site_id: currentSiteId,
        route_id: draft.route_id || selectedRoute?.route_id || '',
        event_id: eventRecord.event_id,
        program: protocolDefinition.program,
        submodule: currentProgram === 'terrestrial_vertebrates' ? activeVertebrateSubmoduleId : (protocolDefinition.defaultTaxonGroup || ''),
        protocol: protocolDefinition.id,
        jurisdiction: exportJurisdiction,
        name: `${draft.route_name || selectedRoute?.name || currentSite?.name || currentProject?.name || 'Survey'} ${new Date().toLocaleTimeString()}`,
        source: 'recorded',
        geometry: { type: 'LineString', coordinates: draft.points },
        point_times: draft.point_times,
        started_at: draft.started_at,
        ended_at: endedAt,
        distance_m: lineDistanceMeters(draft.points),
        observer: draft.observer || '',
        weather: draft.weather || '',
        notes: draft.notes || '',
        extra: draft.extra || buildProtocolExtra('event'),
      }
      try {
        if (isOnline) {
          const response = await createSurveyTrack(payload)
          setSurveyState((current) => replaceEntity(current, 'track', response.track))
        } else {
          setSurveyState((current) => upsertLocalEntity(current, 'track', payload))
        }
      } catch (err) {
        setSurveyState((current) => upsertLocalEntity(current, 'track', payload))
        setError(getApiErrorMessage(err, isZh ? '轨迹已保存到本地并加入同步队列。' : 'Track saved locally and queued for sync.'))
      }
    }
    setSurveyState((current) => ({ ...current, activeTrackDraft: null }))
    setTransectSession((current) => current.started_at
      ? { ...current, ended_at: current.ended_at || endedAt }
      : current)
    syncDraftIntoUi(null)
  }

  function exportRoute(record, format) {
    if (!record) return
    if (format === 'gpx') {
      downloadTextFile(`${record.name || (locale === 'zh' ? '路线' : 'route')}.gpx`, buildGpx(record), 'application/gpx+xml;charset=utf-8')
      return
    }
    downloadTextFile(
      `${record.name || (locale === 'zh' ? '路线' : 'route')}.geojson`,
      JSON.stringify(buildFeatureCollection(record), null, 2),
      'application/geo+json;charset=utf-8',
    )
  }

  async function handleExportRouteReport(format) {
    if (!selectedRoute?.route_id || !isOnline) return
    if (activeTaxonomyPackageStatus.isBlocked) {
      setError(buildTaxonomyGateBlockingMessage(activeTaxonomyPackageStatus, protocolDefinition, activeJurisdictionLabel, locale))
      return
    }
    setExportingRouteReportFormat(format)
    setError(null)
    try {
      const exported = await exportSurveyRouteReport(selectedRoute.route_id, format)
      downloadBlobFile(
        exported.blob,
        exported.filename || `${selectedRoute.name || (locale === 'zh' ? '路线报告' : 'route-report')}.${format}`,
      )
    } catch (err) {
      setError(getApiErrorMessage(err, locale === 'zh' ? `无法导出 ${format.toUpperCase()} 路线/站点报告。` : `Unable to export the ${format.toUpperCase()} route or station report.`))
    } finally {
      setExportingRouteReportFormat('')
    }
  }

  function formatElapsed(totalSeconds) {
    const h = Math.floor(totalSeconds / 3600)
    const m = Math.floor((totalSeconds % 3600) / 60)
    const s = totalSeconds % 60
    return h > 0
      ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
      : `${m}:${String(s).padStart(2, '0')}`
  }

  function handleStartSurvey() {
    const startedAt = new Date().toISOString()
    setTransectSession({
      started_at: startedAt,
      ended_at: '',
      observer: transectForm.observer || observationForm.observer || '',
      weather: transectForm.weather || '',
      notes: transectForm.notes || '',
      route_id: selectedRoute?.route_id || '',
    })
    setObservationForm((current) => ({
      ...current,
      observer: transectForm.observer || current.observer,
    }))
    if (protocolDefinition.supportsTrack && !watchRef.current) {
      handleStartTrack()
    }
    setSurveyActive(true)
    setElapsedSeconds(0)
    setShowObservationSheet(false)
    setSurveyStep('survey')
  }

  function handleEndSurvey() {
    if (trackStatus === 'recording') {
      void stopTrackOnlineAware()
    }
    setTransectSession((current) => ({
      ...current,
      ended_at: current.started_at ? new Date().toISOString() : '',
    }))
    setSurveyActive(false)
    setSurveyStep('records')
  }

  async function handleCameraAndObserve() {
    if (nativeMobile) {
      setSerializingMedia(true)
      setError(null)
      try {
        const attachment = await capturePhotoAttachment(CameraSource.Camera)
        if (attachment) {
          await pulseFeedback(ImpactStyle.Light)
          appendDraftAttachments([attachment])
        }
      } catch (err) {
        setError(getApiErrorMessage(err, isZh ? '无法拍摄照片' : 'Unable to capture photo'))
      } finally {
        setSerializingMedia(false)
      }
    }
    setShowObservationSheet(true)
  }

  const canStartSurvey = !!currentProjectId
  const stepTabs = [
    { id: 'setup',  icon: ListChecks,   label: isZh ? '准备' : 'Setup',   disabled: false },
    { id: 'survey', icon: Compass,       label: isZh ? '调查' : 'Survey',  disabled: !canStartSurvey },
    { id: 'records', icon: ClipboardList, label: isZh ? '记录' : 'Records', disabled: false },
  ]

  return (
    <div className="space-y-5">
      {/* ═══ 顶部导航栏 ═══ */}
      <section className="card-padded">
        <div className="flex items-center gap-3">
          <div className="segmented-control flex-1">
            {stepTabs.map((tab) => {
              const isActive = surveyStep === tab.id
              const Icon = tab.icon
              return (
                <button
                  key={tab.id}
                  onClick={() => { if (!tab.disabled) setSurveyStep(tab.id) }}
                  disabled={tab.disabled}
                  className={isActive ? 'active' : ''}
                  data-testid={`step-tab-${tab.id}`}
                  data-active={isActive ? 'true' : 'false'}
                >
                  <Icon className="h-[15px] w-[15px]" />
                  {tab.label}
                </button>
              )
            })}
          </div>
          <div className="flex items-center gap-1.5">
            <span
              data-testid="network-chip"
              data-state={isOnline ? 'online' : 'offline'}
              className={`status-dot ${isOnline ? 'status-dot-online' : 'status-dot-warning'}`}
              title={isOnline ? copy.online : copy.offline}
            />
            <button
              onClick={handlePullSync}
              disabled={!isOnline || loadingSync}
              className="btn-ghost btn-icon disabled:opacity-30"
              data-testid="sync-pull"
            >
              {loadingSync ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            </button>
            <button
              onClick={handlePushSync}
              disabled={!isOnline || loadingSync || surveyState.syncQueue.length === 0}
              className="btn-primary btn-icon disabled:opacity-30"
              data-testid="sync-push"
              data-pending-count={surveyState.syncQueue.length}
            >
              <Save className="h-4 w-4" />
            </button>
          </div>
        </div>
      </section>

      <StatusBanner tone="error" message={error} />
      {surveyStep === 'records' && (
        <StatusBanner tone="warning" message={taxonomyGateWarningMessage} />
      )}

      {/* ═══ STEP 1: 准备 — iOS 钻入导航 ═══ */}
      {surveyStep === 'setup' && (
        <>
          {/* iOS 导航栏 + 面包屑 */}
          <div className="px-1">
            {setupLevel !== 'projects' && (
              <button
                onClick={() => setSetupLevel(setupLevel === 'routes' ? 'sites' : 'projects')}
                className="mb-1 inline-flex items-center gap-0.5 rounded-lg px-1 py-1.5 text-[15px] font-normal text-[#0A84FF] transition-colors active:text-[#0A84FF]/60"
              >
                <ChevronLeft className="h-5 w-5 -ml-1" />
                {setupLevel === 'routes'
                  ? (currentProject?.name || (isZh ? '站点' : 'Sites'))
                  : (isZh ? '项目' : 'Projects')}
              </button>
            )}
            <h2
              data-testid="setup-level-header"
              data-level={setupLevel}
              className="text-[22px] font-bold tracking-tight text-white"
            >
              {setupLevel === 'projects' && (isZh ? '选择项目' : 'Select Project')}
              {setupLevel === 'sites' && (isZh ? '选择站点' : 'Select Site')}
              {setupLevel === 'routes' && (isZh ? '选择路线' : 'Select Route')}
            </h2>
            {setupLevel === 'sites' && (
              <p className="mt-0.5 text-[13px] text-white/40">{currentProject?.name}</p>
            )}
            {setupLevel === 'routes' && (
              <p className="mt-0.5 text-[13px] text-white/40">
                {currentProject?.name} › {projectSites.find((s) => s.site_id === currentSiteId)?.name}
              </p>
            )}
          </div>

          {/* iOS Grouped Inset List */}
          <section className="overflow-hidden rounded-2xl border border-white/[0.06] bg-white/[0.03]">
            {/* ── Level 1: 项目列表 ── */}
            {setupLevel === 'projects' && (
              <>
                {surveyState.projects.length === 0 && (
                  <div className="flex flex-col items-center gap-3 px-6 py-14">
                    <div className="flex h-14 w-14 items-center justify-center rounded-full bg-white/[0.06]">
                      <FolderOpen className="h-7 w-7 text-white/30" />
                    </div>
                    <p className="text-[15px] font-medium text-white/60">{isZh ? '暂无项目' : 'No Projects'}</p>
                    <p className="text-center text-[13px] leading-snug text-white/30">{isZh ? '请联系管理员在设置页创建项目' : 'Ask admin to create projects in Settings'}</p>
                  </div>
                )}
                {surveyState.projects.map((project, idx) => {
                  const isActive = project.project_id === currentProjectId
                  const sitesCount = toArray(surveyState.sites).filter((s) => s.project_id === project.project_id).length
                  return (
                    <button
                      key={project.project_id}
                      data-testid={`project-row-${project.project_id}`}
                      data-testid-role="project-row"
                      data-active={isActive ? 'true' : 'false'}
                      onClick={() => {
                        setSurveyState((current) => ({
                          ...current,
                          activeProjectId: project.project_id,
                          activeSiteId: '',
                          activeRouteId: '',
                          activeEventId: '',
                        }))
                        setSetupLevel('sites')
                      }}
                      className={`flex w-full items-center gap-3.5 px-4 py-[14px] text-left transition-colors active:bg-white/[0.06] ${
                        idx > 0 ? 'border-t border-white/[0.04]' : ''
                      }`}
                    >
                      <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${isActive ? 'bg-[#0A84FF]/20' : 'bg-white/[0.06]'}`}>
                        <FolderOpen className={`h-[18px] w-[18px] ${isActive ? 'text-[#0A84FF]' : 'text-white/50'}`} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <span className="block truncate text-[15px] text-white">{project.name}</span>
                        {project.region && (
                          <span className="block truncate text-[13px] text-white/30">{project.region}</span>
                        )}
                      </div>
                      <span className="shrink-0 text-[13px] text-white/30">{sitesCount}</span>
                      <ChevronLeft className="h-[14px] w-[14px] shrink-0 rotate-180 text-white/20" />
                    </button>
                  )
                })}
              </>
            )}

            {/* ── Level 2: 站点列表 ── */}
            {setupLevel === 'sites' && (
              <>
                {projectSites.length === 0 && (
                  <div className="flex flex-col items-center gap-3 px-6 py-14">
                    <div className="flex h-14 w-14 items-center justify-center rounded-full bg-white/[0.06]">
                      <MapPin className="h-7 w-7 text-white/30" />
                    </div>
                    <p className="text-[15px] font-medium text-white/60">{isZh ? '暂无站点' : 'No Sites'}</p>
                    <p className="text-center text-[13px] leading-snug text-white/30">{isZh ? '请联系管理员在设置页添加站点' : 'Ask admin to add sites in Settings'}</p>
                  </div>
                )}
                {projectSites.map((site, idx) => {
                  const isActive = site.site_id === currentSiteId
                  const hasCoords = site.latitude && site.longitude
                  const routesCount = toArray(surveyState.routes).filter((r) => r.site_id === site.site_id).length
                  return (
                    <button
                      key={site.site_id}
                      data-testid={`site-row-${site.site_id}`}
                      data-testid-role="site-row"
                      data-active={isActive ? 'true' : 'false'}
                      onClick={() => {
                        setSurveyState((current) => ({
                          ...current,
                          activeSiteId: site.site_id,
                          activeRouteId: '',
                          activeEventId: '',
                        }))
                        setSetupLevel('routes')
                      }}
                      className={`flex w-full items-center gap-3.5 px-4 py-[14px] text-left transition-colors active:bg-white/[0.06] ${
                        idx > 0 ? 'border-t border-white/[0.04]' : ''
                      }`}
                    >
                      <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${isActive ? 'bg-[#5E5CE6]/20' : 'bg-white/[0.06]'}`}>
                        <MapPin className={`h-[18px] w-[18px] ${isActive ? 'text-[#5E5CE6]' : 'text-white/50'}`} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <span className="block truncate text-[15px] text-white">{site.name}</span>
                        <span className="block truncate text-[13px] text-white/30">
                          {[site.habitat_type, hasCoords && `${Number(site.latitude).toFixed(3)}, ${Number(site.longitude).toFixed(3)}`].filter(Boolean).join(' · ')}
                        </span>
                      </div>
                      <span className="shrink-0 text-[13px] text-white/30">{routesCount}</span>
                      <ChevronLeft className="h-[14px] w-[14px] shrink-0 rotate-180 text-white/20" />
                    </button>
                  )
                })}
              </>
            )}

            {/* ── Level 3: 路线列表 ── */}
            {setupLevel === 'routes' && (
              <>
                {siteRoutes.length === 0 && (
                  <div className="flex flex-col items-center gap-3 px-6 py-14">
                    <div className="flex h-14 w-14 items-center justify-center rounded-full bg-white/[0.06]">
                      <Route className="h-7 w-7 text-white/30" />
                    </div>
                    <p className="text-[15px] font-medium text-white/60">{isZh ? '暂无路线' : 'No Routes'}</p>
                    <p className="text-center text-[13px] leading-snug text-white/30">{isZh ? '请联系管理员在设置页添加路线' : 'Ask admin to add routes in Settings'}</p>
                  </div>
                )}
                {siteRoutes.map((route, idx) => {
                  const isActive = route.route_id === currentRouteId
                  const lengthM = Math.round(route.length_m || 0)
                  return (
                    <button
                      key={route.route_id}
                      data-testid={`route-row-${route.route_id}`}
                      data-testid-role="route-row"
                      data-active={isActive ? 'true' : 'false'}
                      onClick={() => handleSelectRoute(route.route_id)}
                      className={`flex w-full items-center gap-3.5 px-4 py-[14px] text-left transition-colors active:bg-white/[0.06] ${
                        idx > 0 ? 'border-t border-white/[0.04]' : ''
                      }`}
                    >
                      <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${isActive ? 'bg-[#30D158]/20' : 'bg-white/[0.06]'}`}>
                        <Route className={`h-[18px] w-[18px] ${isActive ? 'text-[#30D158]' : 'text-white/50'}`} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <span className="block truncate text-[15px] text-white">{route.name}</span>
                        <span className="block truncate text-[13px] text-white/30">
                          {[route.route_type, lengthM > 0 && `${lengthM}m`].filter(Boolean).join(' · ')}
                        </span>
                      </div>
                      {isActive && (
                        <span className="shrink-0 text-[13px] font-medium text-[#30D158]">✓</span>
                      )}
                      {!isActive && <ChevronLeft className="h-[14px] w-[14px] shrink-0 rotate-180 text-white/20" />}
                    </button>
                  )
                })}
              </>
            )}
          </section>

          {/* ── 快速开始调查 ── */}
          {currentProjectId && (
            <section className="space-y-3 rounded-2xl border border-white/[0.06] bg-white/[0.03] p-4">
              <h3 className="text-[15px] font-semibold text-white">{isZh ? '准备调查' : 'Prepare Survey'}</h3>

              {/* 选中摘要 */}
              <div className="flex flex-wrap gap-1.5">
                {currentProject && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-[#0A84FF]/10 px-2.5 py-1 text-[12px] text-[#0A84FF]">
                    <FolderOpen className="h-3 w-3" />{currentProject.name}
                  </span>
                )}
                {currentSite && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-[#5E5CE6]/10 px-2.5 py-1 text-[12px] text-[#5E5CE6]">
                    <MapPin className="h-3 w-3" />{currentSite.name}
                  </span>
                )}
                {selectedRoute && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-[#30D158]/10 px-2.5 py-1 text-[12px] text-[#30D158]">
                    <Route className="h-3 w-3" />{selectedRoute.name}
                  </span>
                )}
              </div>

              {/* 调查人员 */}
              <label className="space-y-1">
                <span className="block text-[12px] text-white/30">{isZh ? '调查人员' : 'Observer'}</span>
                <input
                  data-testid="prep-observer"
                  value={transectForm.observer}
                  onChange={(e) => setTransectForm((c) => ({ ...c, observer: e.target.value }))}
                  placeholder={isZh ? '输入姓名' : 'Enter name'}
                  className="w-full rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-4 py-[11px] text-[15px] text-white placeholder:text-white/25 focus:border-[#0A84FF]/40 focus:outline-none"
                />
              </label>

              {/* 天气 */}
              <label className="space-y-1">
                <span className="block text-[12px] text-white/30">{isZh ? '天气概况' : 'Weather'}</span>
                <input
                  data-testid="prep-weather"
                  value={transectForm.weather}
                  onChange={(e) => setTransectForm((c) => ({ ...c, weather: e.target.value }))}
                  placeholder={isZh ? '晴、多云、小雨…' : 'Sunny, cloudy, light rain…'}
                  className="w-full rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-4 py-[11px] text-[15px] text-white placeholder:text-white/25 focus:border-[#0A84FF]/40 focus:outline-none"
                />
              </label>

              {/* GPS + 时间 */}
              <div className="grid grid-cols-2 gap-2">
                <div className="rounded-[12px] bg-white/[0.04] px-3 py-2.5">
                  <p className="text-[11px] text-white/30">{isZh ? '经纬度' : 'GPS'}</p>
                  <p className="mt-0.5 text-[13px] font-medium tabular-nums text-white/70">
                    {currentPosition
                      ? `${currentPosition.lat.toFixed(5)}, ${currentPosition.lon.toFixed(5)}`
                      : (isZh ? '定位中…' : 'Locating…')}
                  </p>
                </div>
                <div className="rounded-[12px] bg-white/[0.04] px-3 py-2.5">
                  <p className="text-[11px] text-white/30">{isZh ? '当前时间' : 'Time'}</p>
                  <p className="mt-0.5 text-[13px] font-medium tabular-nums text-white/70">
                    {liveTime.toLocaleTimeString(isZh ? 'zh-CN' : 'en', { hour: '2-digit', minute: '2-digit' })}
                  </p>
                </div>
              </div>

              {/* 开始按钮 */}
              <button
                data-testid="prep-start"
                onClick={handleStartSurvey}
                disabled={!transectForm.observer.trim()}
                className="inline-flex w-full items-center justify-center gap-2.5 rounded-[14px] bg-[#30D158] px-6 py-[15px] text-[17px] font-semibold text-white shadow-lg shadow-[#30D158]/20 transition-all active:scale-[0.98] active:bg-[#30D158]/80 disabled:opacity-40 disabled:shadow-none"
              >
                <Play className="h-5 w-5" />
                {isZh ? '开始调查' : 'Start Survey'}
              </button>
              {!transectForm.observer.trim() && (
                <p className="text-center text-[12px] text-white/25">{isZh ? '请先填写调查人员姓名' : 'Enter observer name first'}</p>
              )}
            </section>
          )}
        </>
      )}

      {/* ═══ STEP 2: 调查 — 地图 + 轨迹 + 观测录入 ═══ */}
      {surveyStep === 'survey' && (
        <>
          {/* iOS 状态栏 + 计时器 */}
          <section className="rounded-2xl border border-white/[0.06] bg-white/[0.03] px-4 py-3 backdrop-blur-xl">
            <div className="flex items-center gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="truncate text-[15px] font-semibold text-white">
                    {selectedRoute?.name || currentSite?.name || currentProject?.name || (isZh ? '调查中' : 'Surveying')}
                  </p>
                  {surveyActive && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-[#FF9F0A]/15 px-2 py-0.5 text-[12px] font-medium tabular-nums text-[#FF9F0A]">
                      <Clock className="h-3 w-3" />
                      {formatElapsed(elapsedSeconds)}
                    </span>
                  )}
                </div>
                <p className="mt-0.5 flex items-center gap-1.5 text-[13px] text-white/40">
                  <span>{protocolObservations.length} {isZh ? '观测' : 'obs'}</span>
                  <span>·</span>
                  <span>{protocolTracks.length} {isZh ? '轨迹' : 'tracks'}</span>
                  {trackInfo.distance_m > 0 && (
                    <>
                      <span>·</span>
                      <span className="tabular-nums">{Math.round(trackInfo.distance_m)}m</span>
                    </>
                  )}
                  {currentPosition && (
                    <>
                      <span>·</span>
                      <span className="tabular-nums">{currentPosition.lat.toFixed(4)}, {currentPosition.lon.toFixed(4)}</span>
                    </>
                  )}
                </p>
              </div>
              <div className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12px] font-medium ${
                trackStatus === 'recording'
                  ? 'bg-[#FF453A]/15 text-[#FF453A]'
                  : 'bg-white/[0.06] text-white/40'
              }`}>
                {trackStatus === 'recording' && <span className="h-2 w-2 animate-pulse rounded-full bg-[#FF453A]" />}
                {trackStatus === 'recording' ? (isZh ? '录制中' : 'REC') : (isZh ? '待机' : 'Idle')}
              </div>
              <button
                data-testid="survey-end"
                onClick={handleEndSurvey}
                className="shrink-0 rounded-[10px] bg-[#FF453A]/15 px-3.5 py-2 text-[13px] font-medium text-[#FF453A] transition-colors active:bg-[#FF453A]/25"
              >
                <Square className="mr-1 inline h-3.5 w-3.5" />{isZh ? '结束' : 'End'}
              </button>
            </div>
          </section>

          {/* 地图 */}
          <section className="overflow-hidden rounded-2xl border border-white/[0.06]">
            <FieldSurveyMap
              center={mapCenter}
              tileUrl={tileUrl}
              attribution={tileAttribution}
              sites={projectSites}
              routes={selectedRoute ? [selectedRoute] : siteRoutes}
              observations={routeObservations}
              tracks={routeTracks}
              liveTrack={liveTrack}
              userPosition={currentPosition}
            />
          </section>

          {/* 协议事件字段（风力/云量/降水/生境等） */}
          {(() => { const lp = localizeProtocol(protocolDefinition, locale); return lp.eventFields.length > 0 && (
            <section className="space-y-2 rounded-2xl border border-white/[0.06] bg-white/[0.03] p-4">
              <h3 className="text-[13px] font-medium text-white/40">{isZh ? '调查表字段' : 'Survey Form Fields'}</h3>
              <div className="grid gap-2 sm:grid-cols-2">
                {lp.eventFields.map((field) => (
                  <label key={field.key} className="space-y-1">
                    <span className="block text-[12px] text-white/30">{field.label}</span>
                    {field.options ? (
                      <ComboField
                        value={protocolState.event[field.key] || ''}
                        onChange={(val) => handleProtocolEventFieldChange(field.key, val)}
                        options={field.options}
                        placeholder={field.placeholder || field.label}
                      />
                    ) : (
                      <input
                        type={field.type || 'text'}
                        value={protocolState.event[field.key] || ''}
                        onChange={(e) => handleProtocolEventFieldChange(field.key, e.target.value)}
                        placeholder={field.placeholder || field.label}
                        className="w-full rounded-[12px] border border-white/[0.06] bg-white/[0.04] px-4 py-[11px] text-[15px] text-white placeholder:text-white/25 focus:border-[#0A84FF]/40 focus:outline-none"
                      />
                    )}
                  </label>
                ))}
              </div>
            </section>
          ); })()}

          {/* 观测录入 — 点击相机/+号后展开 */}
          {showObservationSheet ? (
            <section className="space-y-4">
              <ObservationFormPanel
                copy={copy}
                protocolDefinition={protocolDefinition}
                locale={locale}
                selectedRoute={selectedRoute}
                currentProjectId={currentProjectId}
                observationForm={observationForm}
                onChangeObservationForm={setObservationForm}
                speciesSuggestions={speciesSuggestions}
                taxonomyCatalog={taxonomyCatalog}
                availableTaxaOptions={availableTaxaOptions}
                protocolState={protocolState}
                onRecordFieldChange={handleProtocolRecordFieldChange}
                attachments={attachments}
                serializingMedia={serializingMedia}
                audioCaptureStatus={audioCaptureStatus}
                nativeMobile={nativeMobile}
                routeObservations={routeObservations}
                onAddAttachments={handleAddAttachments}
                onStartAudioCapture={handleStartAudioCapture}
                onStopAudioCapture={handleStopAudioCapture}
                onCapturePhoto={handleCapturePhoto}
                validationMissing={recordValidationMissing}
                onSaveObservation={async () => {
                  const saved = await saveObservationOnlineAware()
                  if (saved) setShowObservationSheet(false)
                }}
              />
              <button
                onClick={() => setShowObservationSheet(false)}
                className="inline-flex w-full items-center justify-center gap-2 rounded-[12px] bg-white/[0.06] px-4 py-3 text-[14px] text-white/50 transition-colors active:bg-white/10"
              >
                {isZh ? '收起' : 'Collapse'}
              </button>
            </section>
          ) : (
            /* 浮动相机 / + 号 FAB */
            <section className="flex flex-col items-center gap-3 py-4">
              <button
                data-testid="obs-fab"
                onClick={handleCameraAndObserve}
                className="flex h-[72px] w-[72px] items-center justify-center rounded-full bg-[#0A84FF] shadow-lg shadow-[#0A84FF]/30 transition-all active:scale-95 active:bg-[#0A84FF]/80"
              >
                {nativeMobile ? <Camera className="h-8 w-8 text-white" /> : <Plus className="h-8 w-8 text-white" />}
              </button>
              <p className="text-[13px] text-white/30">
                {nativeMobile
                  ? (isZh ? '拍照并记录物种' : 'Photo & record species')
                  : (isZh ? '添加观测记录' : 'Add observation')}
              </p>
              {/* 最近观测简约列表 */}
              {routeObservations.length > 0 && (
                <div className="mt-2 w-full space-y-1">
                  <p className="px-1 text-[12px] text-white/25">{isZh ? '最近记录' : 'Recent'}</p>
                  {routeObservations.slice(0, 4).map((obs, idx) => (
                    <div key={obs.observation_id || idx} className="flex items-center gap-2 rounded-[10px] bg-white/[0.03] px-3 py-2">
                      <span className="min-w-0 flex-1 truncate text-[13px] text-white/60">
                        {obs.chinese_name || obs.scientific_name || obs.english_name || (isZh ? '未知物种' : 'Unknown')}
                      </span>
                      <span className="shrink-0 text-[12px] tabular-nums text-white/25">×{obs.count || 1}</span>
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}

          {/* 轨迹面板 */}
          <TrackPanel
            copy={copy}
            trackStatus={trackStatus}
            trackInfo={trackInfo}
            selectedRoute={selectedRoute}
            protocolDefinition={protocolDefinition}
            hasActiveTrackDraft={hasActiveTrackDraft}
            latestTrack={latestTrack}
            onStart={handleStartTrack}
            onStop={stopTrackOnlineAware}
            locale={locale}
          />
        </>
      )}

      {/* ═══ STEP 3: 记录 — 观测列表 + 审核 + 导出 + 同步 ═══ */}
      {surveyStep === 'records' && (
        <>
          {/* iOS 导航栏 */}
          <div className="px-1">
            <button
              onClick={() => { setSurveyStep('survey'); if (transectSession.started_at && !transectSession.ended_at) setSurveyActive(true) }}
              className="mb-1 inline-flex items-center gap-0.5 rounded-lg px-1 py-1.5 text-[15px] font-normal text-[#0A84FF] transition-colors active:text-[#0A84FF]/60"
            >
              <ChevronLeft className="h-5 w-5 -ml-1" />
              {isZh ? '继续调查' : 'Resume Survey'}
            </button>
            <div className="flex items-center justify-between">
              <h2 className="text-[22px] font-bold tracking-tight text-white">{isZh ? '调查记录' : 'Records'}</h2>
              <span className="text-[13px] text-white/30">
                {protocolObservations.length} {isZh ? '观测' : 'obs'} · {protocolTracks.length} {isZh ? '轨迹' : 'tracks'}
              </span>
            </div>
          </div>

          <ObservationListPanel
            locale={locale}
            isOnline={isOnline}
            projectId={currentProjectId}
            siteId={currentSiteId}
            onDataChanged={handlePullSync}
          />

          <section className="space-y-4">
            {isTerrestrialVertebrateProtocol && (
              <VertebrateReviewPanel
                protocolDefinition={protocolDefinition}
                exportJurisdiction={exportJurisdiction}
                locale={locale}
                onChangeJurisdiction={setExportJurisdiction}
                eventValidationMissing={eventValidationMissing}
                recordValidationMissing={recordValidationMissing}
                eventPayloadDraft={eventPayloadDraft}
                currentRecordPayloadDraft={currentRecordPayloadDraft}
                currentMatchedSpecies={currentMatchedSpecies}
                currentRecordMaskPreview={currentRecordMaskPreview}
                recentVertebrateRecordPreviews={recentVertebrateRecordPreviews}
                maskedPreviewCount={maskedPreviewCount}
                latestProtocolEvent={latestProtocolEvent}
                latestProtocolExportJob={latestProtocolExportJob}
                vertebrateExportResult={vertebrateExportResult}
                taxonomyGateByJurisdiction={taxonomyGateByJurisdiction}
                savingReviewEvent={savingReviewEvent}
                exportingVertebrateJurisdiction={exportingVertebrateJurisdiction}
                isOnline={isOnline}
                onSaveReview={saveReviewEventOnlineAware}
                onExport={handleCreateVertebrateExport}
              />
            )}

            {!isTerrestrialVertebrateProtocol && (
              <ProtocolExportPanel
                protocolDefinition={protocolDefinition}
                exportJurisdiction={exportJurisdiction}
                locale={locale}
                onChangeJurisdiction={(nextJurisdiction) => setExportJurisdiction(normalizeJurisdiction(nextJurisdiction, EXPORT_JURISDICTIONS[0].id))}
                taxonomyPackage={activeTaxonomyPackage}
                taxonomyPackageNote={taxonomyPackageNote}
                taxonomyGateByJurisdiction={taxonomyGateByJurisdiction}
                observationCount={protocolObservations.length}
                trackCount={protocolTracks.length}
                latestProtocolEvent={latestProtocolEvent}
                latestProtocolExportJob={latestProtocolExportJob}
                savingEvent={savingReviewEvent}
                exportingJurisdiction={exportingVertebrateJurisdiction}
                isOnline={isOnline}
                onSaveEvent={saveReviewEventOnlineAware}
                onExport={handleCreateProtocolExport}
              />
            )}

            {(protocolDefinition.requiresAsset || protocolDefinition.supportsTrack) && (
              <RouteReportPanel
                copy={copy}
                locale={locale}
                selectedRoute={selectedRoute}
                routeReport={routeReport}
                routeReportError={routeReportError}
                routeReportStatus={routeReportStatus}
                isOnline={isOnline}
                exportingFormat={exportingRouteReportFormat}
                taxonomyGateBlocked={activeTaxonomyPackageStatus.isBlocked}
                taxonomyGateMessage={taxonomyGateWarningMessage}
                onExport={handleExportRouteReport}
              />
            )}
          </section>

          {/* 工具/媒体/同步 */}
          <section className="grid grid-cols-2 gap-4 xl:grid-cols-3">
            <MapToolsPanel
              copy={copy}
              activeMapPackages={activeMapPackages}
              selectedRoute={selectedRoute}
              currentProjectId={currentProjectId}
              downloadingTiles={downloadingTiles}
              importingRoute={importingRoute}
              onPreloadTiles={preloadTilesOnlineAware}
              onImportRoute={handleImportRoute}
              onExportRoute={exportRoute}
            />
            <MediaInboxPanel copy={copy} locale={locale} mediaInbox={surveyState.mediaInbox} />
            <SyncPanel copy={copy} surveyState={surveyState} locale={locale} />
          </section>

          {/* iOS-style 返回准备 */}
          <section className="flex justify-center px-4 py-4">
            <button
              onClick={() => { setSurveyStep('setup'); setSetupLevel('projects') }}
              className="inline-flex w-full items-center justify-center gap-2 rounded-[14px] bg-white/[0.06] px-6 py-[14px] text-[15px] font-medium text-white/60 transition-colors active:bg-white/10"
            >
              <ListChecks className="h-[18px] w-[18px]" />
              {isZh ? '新调查（返回准备）' : 'New Survey (Back to Setup)'}
            </button>
          </section>
        </>
      )}
    </div>
  )
}
