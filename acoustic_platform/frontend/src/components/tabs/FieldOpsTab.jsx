import React, { useDeferredValue, useEffect, useMemo, useRef, useState } from 'react'
import { MapPinned } from 'lucide-react'
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
  getSurveyDesignAssets,
  getSurveyProtocols,
  getSurveyRouteSummary,
  getSurveyTaxonomyPackages,
  importSurveyRoute,
  pullSurveySync,
  pushSurveySync,
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
  applySyncResult,
  buildFeatureCollection,
  buildGpx,
  createDefaultProject,
  deriveSurveyTaxonomyPackageStatus,
  downloadTextFile,
  filterByProject,
  filterBySite,
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
import { DEFAULT_SURVEY_MODULE_ID, FIELD_RELEASE_MODE, SURVEY_MODULES } from '../../constants'

import {
  TAXA,
  DEFAULT_REMOTE_TILE_URL,
  DEFAULT_FIELD_TILE_PROXY_URL,
  PROGRAM_OPTIONS,
  TERRESTRIAL_VERTEBRATE_PROTOCOLS,
  VERTEBRATE_SUBMODULES,
  EXPORT_JURISDICTIONS,
  PROTOCOL_OPTIONS,
  COPY,
} from '../fieldops/constants'
import {
  pickLocale,
  toArray,
  getVertebrateSubmoduleById,
  deriveVertebrateSubmoduleId,
  resolveVertebrateSubmodule,
  buildProtocolCatalog,
  mergeTaxonomyCatalogEntries,
  findSpeciesMatch,
  createEmptyTransectSession,
  buildProtocolFieldState,
  getProtocolDefinition,
  createProtocolState,
  resolveProtocolSelection,
  normalizeProtocolFieldValues,
  matchesActiveSubmodule,
  matchesProtocolObservation,
  matchesProtocolTrack,
  getMatchingTaxonomyPackages,
  downloadBlobFile,
  getSpeciesDisplayName,
  splitObserverNames,
  getRequiredFieldLabels,
  buildMaskPreview,
  sortByRecent,
  buildTaxonomyGateWarningMessage,
  buildTaxonomyMetricNote,
  buildTaxonomyGateBlockingMessage,
} from '../fieldops/helpers'

import HeaderPanel from '../fieldops/HeaderPanel'
import ProtocolPanel from '../fieldops/ProtocolPanel'
import PilotFlowPanel from '../fieldops/PilotFlowPanel'
import EssentialWorkflowPanel from '../fieldops/EssentialWorkflowPanel'
import ProjectManagementPanel from '../fieldops/ProjectManagementPanel'
import SurveyEventPanel from '../fieldops/SurveyEventPanel'
import OfflineMapPanel from '../fieldops/OfflineMapPanel'
import ObservationFormPanel from '../fieldops/ObservationFormPanel'
import TrackingPanel from '../fieldops/TrackingPanel'
import MediaPanel from '../fieldops/MediaPanel'
import SyncStatusPanel from '../fieldops/SyncStatusPanel'
import RouteReportPanel from '../fieldops/RouteReportPanel'
import VertebrateReviewPanel from '../fieldops/VertebrateReviewPanel'
import ProtocolExportPanel from '../fieldops/ProtocolExportPanel'
import FieldSurveyMap from '../fieldops/FieldSurveyMap'
import MetricCard from '../fieldops/MetricCard'

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

  // ── Core state ──
  const [surveyState, setSurveyState] = useState(() => loadSurveyState())
  const [speciesCatalog, setSpeciesCatalog] = useState([])
  const [speciesSuggestions, setSpeciesSuggestions] = useState([])
  const [error, setError] = useState(null)
  const [loadingSync, setLoadingSync] = useState(false)
  const [downloadingTiles, setDownloadingTiles] = useState(false)
  const [importingRoute, setImportingRoute] = useState(false)
  const [serializingMedia, setSerializingMedia] = useState(false)
  const [audioCaptureStatus, setAudioCaptureStatus] = useState('idle')
  const [currentPosition, setCurrentPosition] = useState(null)
  const [networkOnline, setNetworkOnline] = useState(typeof navigator === 'undefined' ? true : navigator.onLine)
  const [liveTrack, setLiveTrack] = useState(null)
  const [trackStatus, setTrackStatus] = useState('idle')
  const [trackInfo, setTrackInfo] = useState({ points: 0, distance_m: 0 })
  const watchRef = useRef(null)
  const audioRecorderRef = useRef(null)
  const audioStreamRef = useRef(null)
  const audioChunksRef = useRef([])
  const hydratedRef = useRef(false)
  const defaultProjectInitRef = useRef(false)
  const trackDraftRef = useRef(createEmptyTrackDraft())
  const attachmentsRef = useRef([])

  // ── Form state ──
  const [projectForm, setProjectForm] = useState({ name: '', region: '' })
  const [siteForm, setSiteForm] = useState({ name: '', habitat_type: '', latitude: '', longitude: '' })
  const [transectForm, setTransectForm] = useState({ observer: '', weather: '', notes: '' })
  const [transectSession, setTransectSession] = useState(() => createEmptyTransectSession())
  const [protocolState, setProtocolState] = useState(() => {
    const storedSurveyState = loadSurveyState()
    const seededSelection = resolveProtocolSelection(
      storedSurveyState.activeProgram || activeModule,
      storedSurveyState.activeProtocol || '',
    )
    return createProtocolState(seededSelection.id)
  })
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
  const [bootstrapReady, setBootstrapReady] = useState(false)
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
  const deferredSpeciesQuery = useDeferredValue(observationForm.species_text.trim())

  // ── Track draft helpers ──
  function syncDraftIntoUi(draft) {
    trackDraftRef.current = draft || createEmptyTrackDraft()
    setLiveTrack(
      draft?.points?.length > 1
        ? { geometry: { type: 'LineString', coordinates: [...draft.points] }, started_at: draft.started_at }
        : null,
    )
    setTrackInfo({ points: draft?.points?.length || 0, distance_m: lineDistanceMeters(draft?.points || []) })
    setTrackStatus(draft?.tracking_status === 'recording' ? 'recording' : draft?.tracking_status === 'paused' ? 'paused' : 'idle')
    if (!draft) return
    setTransectSession({
      route_id: draft.route_id || '',
      observer: draft.observer || '',
      weather: draft.weather || '',
      notes: draft.notes || '',
      started_at: draft.started_at || '',
      ended_at: '',
    })
  }

  function setStoredTrackDraft(nextDraft) {
    const normalized = normalizeTrackDraft(nextDraft)
    setSurveyState((current) => ({ ...current, activeTrackDraft: normalized }))
    syncDraftIntoUi(normalized)
  }

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

  async function clearTrackWatch() {
    const currentWatch = watchRef.current
    watchRef.current = null
    if (!currentWatch) return
    if (currentWatch.kind === 'native') { await stopNativePositionWatch(currentWatch.id); return }
    if (currentWatch.kind === 'web' && navigator?.geolocation && currentWatch.id != null) {
      navigator.geolocation.clearWatch(currentWatch.id)
    }
  }

  async function pauseTrackDraft(message, fallbackDraft = null) {
    await clearTrackWatch()
    const pausedDraft = normalizeTrackDraft({
      ...(trackDraftRef.current || fallbackDraft || createEmptyTrackDraft()),
      tracking_status: 'paused',
    })
    if (pausedDraft) setStoredTrackDraft(pausedDraft)
    if (message) setError(message)
  }

  function handleTrackPoint(position) {
    const timestamp = new Date(position.timestamp || Date.now()).toISOString()
    const nextDraft = normalizeTrackDraft({
      ...(trackDraftRef.current || createEmptyTrackDraft()),
      points: [...(trackDraftRef.current?.points || []), [position.lon, position.lat]],
      point_times: [...(trackDraftRef.current?.point_times || []), timestamp],
      tracking_status: 'recording',
    })
    if (!nextDraft) return
    setCurrentPosition({ lat: position.lat, lon: position.lon, accuracy: position.accuracy, timestamp: position.timestamp || Date.now() })
    setStoredTrackDraft(nextDraft)
  }

  // ── Effects ──
  useEffect(() => {
    saveSurveyState(surveyState)
    if (!nativeMobile || nativeHydrationComplete) saveNativeSurveyState(surveyState).catch(() => {})
  }, [nativeHydrationComplete, nativeMobile, surveyState])

  useEffect(() => {
    const restoredAttachments = resolveDraftAttachments(surveyState.mediaInbox, surveyState.activeDraftAttachmentIds)
    const restoredIds = normalizeAttachmentIds(restoredAttachments.map((item) => item?.media_id))
    const currentIds = normalizeAttachmentIds(attachmentsRef.current.map((item) => item?.media_id))
    if (attachmentListsMatch(currentIds, restoredIds)) return
    attachmentsRef.current = restoredAttachments
    setAttachments(restoredAttachments)
  }, [surveyState.activeDraftAttachmentIds, surveyState.mediaInbox])

  useEffect(() => {
    if (!nativeMobile) { setNativeHydrationComplete(true); return undefined }
    let cancelled = false
    loadNativeSurveyState()
      .then((nativeState) => { if (!nativeState || cancelled) return; setSurveyState((current) => mergeStoredSurveyState(current, nativeState)) })
      .catch(() => {})
      .finally(() => { if (!cancelled) setNativeHydrationComplete(true) })
    return () => { cancelled = true }
  }, [nativeMobile])

  useEffect(() => {
    if (!networkOnline) return
    let cancelled = false
    getSurveyProtocols()
      .then((data) => { if (cancelled || !Array.isArray(data?.protocols) || data.protocols.length === 0) return; setSurveyState((current) => ({ ...current, protocols: data.protocols })) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [networkOnline])

  useEffect(() => {
    if (nativeMobile) {
      requestNativeCurrentPosition().then((position) => { if (position) setCurrentPosition(position) }).catch(() => {})
      return
    }
    if (typeof navigator === 'undefined' || !navigator.geolocation) return
    navigator.geolocation.getCurrentPosition(
      (position) => { setCurrentPosition({ lat: position.coords.latitude, lon: position.coords.longitude, accuracy: position.coords.accuracy }) },
      () => {},
      { enableHighAccuracy: true, timeout: 7000, maximumAge: 30000 },
    )
  }, [nativeMobile])

  useEffect(() => {
    if (typeof window === 'undefined') return undefined
    const handleOnline = () => setNetworkOnline(true)
    const handleOffline = () => setNetworkOnline(false)
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    return () => { window.removeEventListener('online', handleOnline); window.removeEventListener('offline', handleOffline) }
  }, [])

  useEffect(() => () => {
    if (audioRecorderRef.current && audioRecorderRef.current.state !== 'inactive') audioRecorderRef.current.stop()
    if (audioStreamRef.current) { audioStreamRef.current.getTracks().forEach((track) => track.stop()); audioStreamRef.current = null }
  }, [])

  useEffect(() => () => { void clearTrackWatch() }, [])

  useEffect(() => {
    const draft = normalizeTrackDraft(surveyState.activeTrackDraft)
    if (!draft) { if (!surveyState.activeTrackDraft && !watchRef.current) syncDraftIntoUi(null); return }
    syncDraftIntoUi(draft)
  }, [surveyState.activeTrackDraft])

  useEffect(() => {
    const draft = normalizeTrackDraft(surveyState.activeTrackDraft)
    if (!draft || draft.tracking_status !== 'recording' || watchRef.current) return undefined
    let cancelled = false
    const handleWatchError = (err) => { if (cancelled) return; void pauseTrackDraft(err?.message || 'Unable to record GPS positions.', draft) }
    const startWatch = async () => {
      try {
        if (nativeMobile) {
          const id = await startNativePositionWatch((position) => { if (!cancelled) handleTrackPoint(position) }, handleWatchError)
          if (cancelled) { await stopNativePositionWatch(id); return }
          watchRef.current = { kind: 'native', id }; return
        }
        if (!navigator?.geolocation) { handleWatchError(new Error('Geolocation is not available in this browser.')); return }
        const id = navigator.geolocation.watchPosition(
          (position) => { if (cancelled) return; handleTrackPoint({ lat: position.coords.latitude, lon: position.coords.longitude, accuracy: position.coords.accuracy, timestamp: position.timestamp || Date.now() }) },
          handleWatchError,
          { enableHighAccuracy: true, maximumAge: 0, timeout: 10000 },
        )
        watchRef.current = { kind: 'web', id }
      } catch (err) { handleWatchError(err) }
    }
    void startWatch()
    return () => { cancelled = true }
  }, [nativeMobile, surveyState.activeTrackDraft])

  // ── Derived state ──
  const isOnline = networkOnline
  const currentProjectId = surveyState.activeProjectId || surveyState.projects[0]?.project_id || ''
  const projectSites = useMemo(() => filterByProject(surveyState.sites, currentProjectId), [surveyState.sites, currentProjectId])
  const currentSiteId = surveyState.activeSiteId || projectSites[0]?.site_id || ''
  const currentProject = surveyState.projects.find((item) => item.project_id === currentProjectId) || null
  const currentSite = projectSites.find((item) => item.site_id === currentSiteId) || null
  const protocolCatalog = useMemo(() => buildProtocolCatalog(surveyState.protocols), [surveyState.protocols])
  const taxonomyCatalog = useMemo(() => mergeTaxonomyCatalogEntries(speciesCatalog, speciesSuggestions), [speciesCatalog, speciesSuggestions])
  const currentProgram = protocolState.program
  const activeVertebrateSubmoduleId = useMemo(
    () => currentProgram === 'terrestrial_vertebrates' ? deriveVertebrateSubmoduleId(surveyState.activeVertebrateSubmodule, observationForm.taxon_group, protocolState.protocol) : '',
    [currentProgram, observationForm.taxon_group, protocolState.protocol, surveyState.activeVertebrateSubmodule],
  )
  const activeVertebrateSubmodule = useMemo(
    () => currentProgram === 'terrestrial_vertebrates' ? getVertebrateSubmoduleById(activeVertebrateSubmoduleId) : null,
    [activeVertebrateSubmoduleId, currentProgram],
  )
  const visibleProtocols = useMemo(
    () => protocolCatalog.filter((item) => item.program === currentProgram && (currentProgram !== 'terrestrial_vertebrates' || toArray(item.vertebrateSubmodules).length === 0 || toArray(item.vertebrateSubmodules).includes(activeVertebrateSubmoduleId))),
    [activeVertebrateSubmoduleId, currentProgram, protocolCatalog],
  )
  const protocolDefinition = useMemo(() => getProtocolDefinition(protocolState.protocol, protocolCatalog), [protocolCatalog, protocolState.protocol])
  const projectRoutes = useMemo(() => filterByProject(surveyState.routes, currentProjectId), [surveyState.routes, currentProjectId])
  const siteRoutes = useMemo(() => filterBySite(projectRoutes, currentSiteId), [projectRoutes, currentSiteId])
  const siteObservations = useMemo(() => filterBySite(filterByProject(surveyState.observations, currentProjectId), currentSiteId), [surveyState.observations, currentProjectId, currentSiteId])
  const siteTracks = useMemo(() => filterBySite(filterByProject(surveyState.tracks, currentProjectId), currentSiteId), [surveyState.tracks, currentProjectId, currentSiteId])
  const activeObservationTaxonGroups = useMemo(
    () => currentProgram === 'terrestrial_vertebrates' ? [activeVertebrateSubmodule?.taxonGroup].filter(Boolean) : toArray(protocolDefinition.allowedTaxonGroups).filter(Boolean),
    [activeVertebrateSubmodule?.taxonGroup, currentProgram, protocolDefinition.allowedTaxonGroups],
  )
  const availableTaxaOptions = useMemo(() => activeObservationTaxonGroups.length > 0 ? activeObservationTaxonGroups : TAXA, [activeObservationTaxonGroups])
  const protocolObservations = useMemo(() => siteObservations.filter((item) => matchesProtocolObservation(item, protocolDefinition, activeVertebrateSubmoduleId)).filter((item) => !item?.taxon_group || activeObservationTaxonGroups.length === 0 || activeObservationTaxonGroups.includes(item.taxon_group)), [activeObservationTaxonGroups, activeVertebrateSubmoduleId, protocolDefinition, siteObservations])
  const protocolTracks = useMemo(() => siteTracks.filter((item) => matchesProtocolTrack(item, protocolDefinition, activeVertebrateSubmoduleId)), [siteTracks, protocolDefinition, activeVertebrateSubmoduleId])
  const selectedRoute = useMemo(() => {
    const explicitRoute = siteRoutes.find((item) => item.route_id === surveyState.activeRouteId) || null
    if (explicitRoute) return explicitRoute
    return protocolDefinition.requiresAsset ? (siteRoutes[0] || null) : null
  }, [protocolDefinition.requiresAsset, siteRoutes, surveyState.activeRouteId])
  const currentRouteId = selectedRoute?.route_id || ''
  const routeObservations = useMemo(() => protocolObservations.filter((item) => { const linkedRouteId = item.route_id || item.snapped_route_id || ''; return currentRouteId ? linkedRouteId === currentRouteId : true }), [protocolObservations, currentRouteId])
  const routeTracks = useMemo(() => protocolTracks.filter((item) => currentRouteId ? item.route_id === currentRouteId : true), [protocolTracks, currentRouteId])
  const activeMapPackages = useMemo(() => filterByProject(surveyState.mapPackages, currentProjectId), [surveyState.mapPackages, currentProjectId])
  const taxonomyGateByJurisdiction = useMemo(() => Object.fromEntries(EXPORT_JURISDICTIONS.map((option) => [option.id, deriveSurveyTaxonomyPackageStatus(getMatchingTaxonomyPackages(surveyState.taxonomyPackages, protocolDefinition, option.id, activeVertebrateSubmoduleId))])), [surveyState.taxonomyPackages, protocolDefinition, activeVertebrateSubmoduleId])
  const activeTaxonomyPackageStatus = taxonomyGateByJurisdiction[exportJurisdiction] || deriveSurveyTaxonomyPackageStatus([])
  const activeTaxonomyPackage = activeTaxonomyPackageStatus.activePackage
  const activeDesignAssets = useMemo(() => toArray(surveyState.designAssets).filter((item) => item.project_id === currentProjectId).filter((item) => !currentSiteId || item.site_id === currentSiteId).filter((item) => !item.program || item.program === protocolDefinition.program).filter((item) => !item.protocol || item.protocol === protocolDefinition.id).filter((item) => matchesActiveSubmodule(item, protocolDefinition, activeVertebrateSubmoduleId)), [surveyState.designAssets, currentProjectId, currentSiteId, protocolDefinition.program, protocolDefinition.id, activeVertebrateSubmoduleId])
  const activeJurisdictionLabel = EXPORT_JURISDICTIONS.find((item) => item.id === exportJurisdiction)?.label || exportJurisdiction
  const taxonomyGateWarningMessage = useMemo(() => buildTaxonomyGateWarningMessage(activeTaxonomyPackageStatus), [activeTaxonomyPackageStatus])
  const taxonomyPackageNote = useMemo(() => buildTaxonomyMetricNote(activeTaxonomyPackageStatus), [activeTaxonomyPackageStatus])

  useEffect(() => {
    if (!networkOnline || !protocolDefinition.program || !protocolDefinition.id) return undefined
    let cancelled = false
    getSurveyTaxonomyPackages({ jurisdiction: exportJurisdiction, program: protocolDefinition.program, protocol: protocolDefinition.id, submodule: protocolDefinition.program === 'terrestrial_vertebrates' ? activeVertebrateSubmoduleId : '' })
      .then((data) => { if (cancelled) return; setSurveyState((current) => mergeSyncPull(current, { taxonomy_packages: toArray(data?.packages), active_program: protocolDefinition.program, active_protocol: protocolDefinition.id, active_vertebrate_submodule: protocolDefinition.program === 'terrestrial_vertebrates' ? activeVertebrateSubmoduleId : '', active_jurisdiction: exportJurisdiction, pulled_at: current.syncMeta?.lastPulledAt || '' })) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [activeVertebrateSubmoduleId, exportJurisdiction, networkOnline, protocolDefinition.id, protocolDefinition.program])

  const protocolEvents = useMemo(() => toArray(surveyState.events).filter((item) => item.project_id === currentProjectId).filter((item) => !currentSiteId || item.site_id === currentSiteId).filter((item) => (item.program || item.extra?.program || '') === protocolDefinition.program).filter((item) => (item.protocol || item.extra?.protocol || '') === protocolDefinition.id).filter((item) => matchesActiveSubmodule(item, protocolDefinition, activeVertebrateSubmoduleId)).filter((item) => !protocolDefinition.requiresAsset || !selectedRoute?.route_id || (item.route_id || '') === selectedRoute.route_id).sort(sortByRecent), [surveyState.events, currentProjectId, currentSiteId, protocolDefinition.program, protocolDefinition.id, protocolDefinition.requiresAsset, selectedRoute?.route_id, activeVertebrateSubmoduleId])
  const jurisdictionEvents = useMemo(() => protocolEvents.filter((item) => (item.jurisdiction || item.extra?.jurisdiction || 'mainland_china') === exportJurisdiction), [protocolEvents, exportJurisdiction])
  const latestProtocolEvent = useMemo(() => jurisdictionEvents.find((item) => item.event_id === surveyState.activeEventId) || jurisdictionEvents[0] || null, [jurisdictionEvents, surveyState.activeEventId])
  const protocolExportJobs = useMemo(() => toArray(surveyState.exportJobs).filter((item) => item.project_id === currentProjectId).filter((item) => !currentSiteId || !item.filters?.site_id || item.filters.site_id === currentSiteId).filter((item) => !item.filters?.program || item.filters.program === protocolDefinition.program).filter((item) => !item.filters?.protocol || item.filters.protocol === protocolDefinition.id).filter((item) => matchesActiveSubmodule(item, protocolDefinition, activeVertebrateSubmoduleId)).sort(sortByRecent), [surveyState.exportJobs, currentProjectId, currentSiteId, protocolDefinition.program, protocolDefinition.id, activeVertebrateSubmoduleId])
  const latestProtocolExportJob = useMemo(() => protocolExportJobs.find((item) => item.jurisdiction === exportJurisdiction) || protocolExportJobs[0] || null, [protocolExportJobs, exportJurisdiction])
  const latestTrack = routeTracks[0] || protocolTracks[0] || siteTracks[0] || null
  const routeComparison = useMemo(() => { const planned = selectedRoute; const walked = latestTrack; if (!planned || !walked) return null; return { planned_m: planned.length_m || lineDistanceMeters(planned.geometry?.coordinates || []), walked_m: walked.distance_m || lineDistanceMeters(walked.geometry?.coordinates || []) } }, [selectedRoute, latestTrack])
  const transectEffortMinutes = useMemo(() => { if (!transectSession.started_at) return 0; const endTime = transectSession.ended_at || new Date().toISOString(); const started = Date.parse(transectSession.started_at); const ended = Date.parse(endTime); if (!Number.isFinite(started) || !Number.isFinite(ended) || ended < started) return 0; return Math.round((ended - started) / 60000) }, [transectSession])
  const walkStatusLabel = trackStatus === 'recording' ? (copy.walkActive || 'Walk active') : trackStatus === 'paused' ? (copy.walkPaused || 'Walk paused') : (copy.walkIdle || 'Walk idle')
  const hasActiveTrackDraft = Boolean(normalizeTrackDraft(surveyState.activeTrackDraft))
  const selectedRouteLength = Math.round(selectedRoute?.length_m || lineDistanceMeters(selectedRoute?.geometry?.coordinates || []))

  const pilotStatusCards = [
    { title: 'Module', value: PROGRAM_OPTIONS.find((item) => item.id === protocolDefinition.program)?.label || protocolDefinition.program, note: protocolDefinition.label },
    { title: protocolDefinition.assetLabel, value: selectedRoute?.name || (protocolDefinition.requiresAsset ? (copy.routeMissing || 'Route needed') : 'Optional'), note: selectedRoute ? `${selectedRouteLength} m` : protocolDefinition.assetHint },
    { title: copy.effort || 'Effort', value: `${transectEffortMinutes} min`, note: walkStatusLabel },
    { title: copy.recordsOnTransect || 'Records', value: protocolObservations.length, note: `${protocolTracks.length} ${copy.walks || 'walks'}` },
    { title: copy.syncBacklog || 'Sync backlog', value: surveyState.syncQueue.length, note: surveyState.conflicts.length > 0 ? `${surveyState.conflicts.length} ${copy.conflicts || 'conflicts'}` : (surveyState.syncMeta?.lastStatus || 'idle') },
  ]
  const workflowSteps = [
    `1. ${protocolDefinition.assetHint}`,
    protocolDefinition.supportsTrack ? '2. Start a walk so GPS effort and timing stay linked to this protocol.' : '2. Fill the protocol event fields and keep the station or plot metadata together.',
    `3. Save ${protocolDefinition.label.toLowerCase()} records with shared evidence plus protocol-specific details.`,
    copy.syncReportStep || '4. Sync queued work and export the protocol bundle when online.',
  ]
  const activeModuleMeta = (moduleMeta?.id === currentProgram ? moduleMeta : null) || SURVEY_MODULES.find((module) => module.id === currentProgram) || SURVEY_MODULES.find((module) => module.id === DEFAULT_SURVEY_MODULE_ID)
  const moduleLabel = activeModuleMeta?.label?.[locale] || activeModuleMeta?.label?.en || 'Survey module'
  const moduleDescription = activeModuleMeta?.description?.[locale] || activeModuleMeta?.description?.en || ''
  const moduleShellHint = activeModuleMeta?.shellHint?.[locale] || activeModuleMeta?.shellHint?.en || ''
  const moduleProtocols = activeModuleMeta?.protocols?.[locale] || activeModuleMeta?.protocols?.en || []
  const ActiveModuleIcon = activeModuleMeta?.icon || MapPinned

  const mapCenter = useMemo(() => {
    if (currentPosition) return [currentPosition.lat, currentPosition.lon]
    if (currentSite?.latitude != null && currentSite?.longitude != null) return [currentSite.latitude, currentSite.longitude]
    return [platformConfig?.study_region?.center_lat || 24.7, platformConfig?.study_region?.center_lon || 110.5]
  }, [currentPosition, currentSite, platformConfig])

  const remoteTileUrl = platformConfig?.map?.tile_url || DEFAULT_REMOTE_TILE_URL
  const pilotTileProxyUrl = platformConfig?.map?.tile_proxy_url || platformConfig?.map?.tile_proxy_path || DEFAULT_FIELD_TILE_PROXY_URL
  const tileUrl = FIELD_RELEASE_MODE ? pilotTileProxyUrl : remoteTileUrl
  const tileAttribution = platformConfig?.map?.tile_attribution || '&copy; OpenStreetMap contributors'
  const isTerrestrialVertebrateProtocol = TERRESTRIAL_VERTEBRATE_PROTOCOLS.has(protocolDefinition.id)

  const normalizedEventFields = useMemo(() => normalizeProtocolFieldValues(protocolDefinition.eventFields, protocolState.event), [protocolDefinition.eventFields, protocolState.event])
  const eventPayloadDraft = useMemo(() => { const payload = { ...normalizedEventFields }; if (protocolDefinition.id.startsWith('bird_')) payload.weather = transectForm.weather.trim(); return payload }, [normalizedEventFields, protocolDefinition.id, transectForm.weather])
  const eventValidationMissing = useMemo(() => { const missing = getRequiredFieldLabels(protocolDefinition.eventFields, protocolState.event); if (protocolDefinition.id.startsWith('bird_') && !transectForm.weather.trim()) missing.push(copy.weather || 'Weather'); if (protocolDefinition.requiresAsset && !selectedRoute) missing.push(protocolDefinition.assetLabel); return missing }, [copy.weather, protocolDefinition.assetLabel, protocolDefinition.eventFields, protocolDefinition.id, protocolDefinition.requiresAsset, protocolState.event, selectedRoute, transectForm.weather])
  const recordValidationMissing = useMemo(() => { const missing = getRequiredFieldLabels(protocolDefinition.recordFields, protocolState.record); if (!observationForm.unknown_taxon && !observationForm.species_text.trim()) missing.unshift('Species'); return missing }, [observationForm.species_text, observationForm.unknown_taxon, protocolDefinition.recordFields, protocolState.record])
  const activeTaxonomySearchGroup = activeObservationTaxonGroups[0] || protocolDefinition.defaultTaxonGroup || ''
  const currentMatchedSpecies = useMemo(() => findSpeciesMatch(taxonomyCatalog, observationForm.species_text), [observationForm.species_text, taxonomyCatalog])

  useEffect(() => {
    if (!isOnline) return
    let cancelled = false
    searchSurveyTaxonomy({ query: deferredSpeciesQuery, jurisdiction: exportJurisdiction, program: protocolDefinition.program, protocol: protocolDefinition.id, taxon_group: activeTaxonomySearchGroup, limit: deferredSpeciesQuery ? 80 : 250 })
      .then((data) => { if (cancelled) return; const results = toArray(data?.results); setSpeciesSuggestions(results); if (results.length > 0) setSpeciesCatalog((current) => mergeTaxonomyCatalogEntries(current, results)) })
      .catch(() => { if (cancelled) return; setSpeciesSuggestions([]) })
    return () => { cancelled = true }
  }, [activeTaxonomySearchGroup, deferredSpeciesQuery, exportJurisdiction, isOnline, protocolDefinition.id, protocolDefinition.program])

  const currentRecordMaskPreview = useMemo(() => buildMaskPreview({ sensitivity: observationForm.trace_only ? 'review' : '', extra: {} }, currentMatchedSpecies, exportJurisdiction), [currentMatchedSpecies, exportJurisdiction, observationForm.trace_only])
  const currentRecordPayloadDraft = useMemo(() => buildObservationRecordPayload({ matched: currentMatchedSpecies, observedAt: latestProtocolEvent?.started_at || new Date().toISOString(), linkedEventId: latestProtocolEvent?.event_id || '' }), [currentMatchedSpecies, latestProtocolEvent?.event_id, latestProtocolEvent?.started_at, observationForm.behavior, observationForm.count, observationForm.evidence_type, protocolDefinition.id, protocolDefinition.recordFields, protocolState.record])
  const recentVertebrateRecordPreviews = useMemo(() => routeObservations.slice(0, 6).map((record) => { const matched = findSpeciesMatch(taxonomyCatalog, record.scientific_name || record.chinese_name || record.english_name || ''); const recordPayload = record.record_payload || record.extra?.record_payload || { ...normalizeProtocolFieldValues(protocolDefinition.recordFields, record.extra?.record_fields || {}), count: record.count, taxon_id: record.taxon_id || matched?.internal_taxon_id || matched?.taxon_id || '', observation_time: record.observed_at || '', evidence_type: record.evidence_type || '' }; return { record, matched, recordPayload, maskPreview: buildMaskPreview(record, matched, exportJurisdiction) } }), [exportJurisdiction, protocolDefinition.recordFields, routeObservations, taxonomyCatalog])
  const maskedPreviewCount = useMemo(() => recentVertebrateRecordPreviews.filter((item) => item.maskPreview.masked).length, [recentVertebrateRecordPreviews])

  // ── Bootstrap and sync effects ──
  useEffect(() => {
    let cancelled = false
    async function bootstrapSurveyState() {
      if (!isOnline) { if (!cancelled) setBootstrapReady(true); return }
      if (hydratedRef.current) { if (!cancelled) setBootstrapReady(true); return }
      hydratedRef.current = true
      try { await handlePullSync() } finally { if (!cancelled) setBootstrapReady(true) }
    }
    bootstrapSurveyState()
    return () => { cancelled = true }
  }, [isOnline])

  useEffect(() => {
    if (!platformConfig?._loaded || surveyState.projects.length > 0 || !bootstrapReady || defaultProjectInitRef.current) return
    defaultProjectInitRef.current = true
    const defaultProject = createDefaultProject(platformConfig)
    if (isOnline) {
      createSurveyProject(defaultProject)
        .then((response) => { setSurveyState((current) => replaceEntity(current, 'project', response.project, { select: true })) })
        .catch(() => { setSurveyState((current) => upsertLocalEntity(current, 'project', defaultProject)) })
      return
    }
    setSurveyState((current) => upsertLocalEntity(current, 'project', defaultProject))
  }, [bootstrapReady, isOnline, platformConfig, surveyState.projects.length])

  useEffect(() => {
    if (siteRoutes.length === 0) { if (surveyState.activeRouteId) setSurveyState((current) => ({ ...current, activeRouteId: '' })); return }
    if (surveyState.activeRouteId) { if (siteRoutes.some((item) => item.route_id === surveyState.activeRouteId)) return; setSurveyState((current) => ({ ...current, activeRouteId: '' })); return }
    if (!protocolDefinition.requiresAsset) return
    setSurveyState((current) => ({ ...current, activeRouteId: siteRoutes[0]?.route_id || '' }))
  }, [protocolDefinition.requiresAsset, siteRoutes, surveyState.activeRouteId])

  useEffect(() => {
    if (!latestProtocolEvent?.event_id) { if (surveyState.activeEventId) setSurveyState((current) => ({ ...current, activeEventId: '' })); return }
    if (surveyState.activeEventId === latestProtocolEvent.event_id) return
    setSurveyState((current) => ({ ...current, activeEventId: latestProtocolEvent.event_id }))
  }, [latestProtocolEvent?.event_id, surveyState.activeEventId])

  useEffect(() => {
    const storedSelection = resolveProtocolSelection(surveyState.activeProgram || activeModule, surveyState.activeProtocol || '', protocolCatalog)
    if (storedSelection.id !== protocolDefinition.id || storedSelection.program !== protocolDefinition.program) {
      setProtocolState(createProtocolState(storedSelection.id, protocolCatalog))
      setObservationForm((current) => ({ ...current, taxon_group: storedSelection.defaultTaxonGroup, evidence_type: storedSelection.defaultEvidenceType }))
    }
    const normalizedStoredJurisdiction = normalizeJurisdiction(surveyState.activeJurisdiction, EXPORT_JURISDICTIONS[0].id)
    if (normalizedStoredJurisdiction !== exportJurisdiction) setExportJurisdiction(normalizedStoredJurisdiction)
    if (onSelectModule && storedSelection.program !== activeModule) onSelectModule(storedSelection.program)
  }, [surveyState.activeProgram, surveyState.activeProtocol, surveyState.activeJurisdiction, activeModule, protocolCatalog, protocolDefinition.id, protocolDefinition.program, exportJurisdiction, onSelectModule])

  useEffect(() => {
    const seededProtocol = protocolCatalog.find((item) => item.program === activeModule)?.id
    if (!seededProtocol) return
    if (protocolDefinition.program === activeModule) return
    const nextProtocol = getProtocolDefinition(seededProtocol, protocolCatalog)
    setProtocolState(createProtocolState(nextProtocol.id, protocolCatalog))
    setObservationForm((current) => ({ ...current, taxon_group: nextProtocol.defaultTaxonGroup, evidence_type: nextProtocol.defaultEvidenceType }))
  }, [activeModule, protocolCatalog, protocolDefinition.program])

  useEffect(() => {
    setSurveyState((current) => {
      const normalizedCurrentJurisdiction = normalizeJurisdiction(current.activeJurisdiction, EXPORT_JURISDICTIONS[0].id)
      if (current.activeProgram === protocolDefinition.program && current.activeProtocol === protocolDefinition.id && normalizedCurrentJurisdiction === exportJurisdiction) return current
      return { ...current, activeProgram: protocolDefinition.program, activeProtocol: protocolDefinition.id, activeJurisdiction: exportJurisdiction }
    })
  }, [protocolDefinition.program, protocolDefinition.id, exportJurisdiction])

  useEffect(() => { setObservationForm((current) => ({ ...current, taxon_group: activeTaxonomySearchGroup || protocolDefinition.defaultTaxonGroup, evidence_type: current.evidence_type === '' ? protocolDefinition.defaultEvidenceType : current.evidence_type })) }, [activeTaxonomySearchGroup, protocolDefinition.defaultEvidenceType, protocolDefinition.defaultTaxonGroup])

  useEffect(() => { if (currentProgram !== 'terrestrial_vertebrates') return; if (surveyState.activeVertebrateSubmodule === activeVertebrateSubmoduleId) return; setSurveyState((current) => ({ ...current, activeVertebrateSubmodule: activeVertebrateSubmoduleId })) }, [activeVertebrateSubmoduleId, currentProgram, surveyState.activeVertebrateSubmodule])

  useEffect(() => { if (visibleProtocols.some((item) => item.id === protocolDefinition.id)) return; const nextProtocol = visibleProtocols[0]; if (!nextProtocol) return; setProtocolState(createProtocolState(nextProtocol.id, protocolCatalog)); setObservationForm((current) => ({ ...current, taxon_group: activeTaxonomySearchGroup || nextProtocol.defaultTaxonGroup, evidence_type: nextProtocol.defaultEvidenceType })) }, [activeTaxonomySearchGroup, protocolCatalog, protocolDefinition.id, visibleProtocols])

  useEffect(() => { setTransectSession((current) => { if (!current.started_at) return current; if (!selectedRoute || current.route_id === selectedRoute.route_id) return current; return createEmptyTransectSession(transectForm.observer || observationForm.observer || '') }) }, [selectedRoute, transectForm.observer, observationForm.observer])

  useEffect(() => {
    let cancelled = false
    if (!selectedRoute?.route_id) { setRouteReport(null); setRouteReportStatus('idle'); setRouteReportError(''); return undefined }
    if (!isOnline) { setRouteReport(null); setRouteReportStatus('offline'); setRouteReportError(''); return undefined }
    setRouteReportStatus('loading'); setRouteReportError('')
    getSurveyRouteSummary(selectedRoute.route_id)
      .then((data) => { if (cancelled) return; setRouteReport(data?.summary || null); setRouteReportStatus('ready') })
      .catch((err) => { if (cancelled) return; setRouteReport(null); setRouteReportStatus('error'); setRouteReportError(getApiErrorMessage(err, 'Unable to load the route or station report.')) })
    return () => { cancelled = true }
  }, [isOnline, selectedRoute?.route_id])

  useEffect(() => { setVertebrateExportResult(null) }, [protocolDefinition.id, exportJurisdiction, selectedRoute?.route_id])

  // ── Handler functions ──
  async function handlePullSync() {
    if (!isOnline) return
    setLoadingSync(true); setError(null)
    try {
      const [pulled, protocolResponse, taxonomyResponse, designAssetResponse] = await Promise.all([
        pullSurveySync(surveyState.syncMeta?.lastPulledAt || ''),
        getSurveyProtocols({ program: protocolDefinition.program }),
        getSurveyTaxonomyPackages({ jurisdiction: exportJurisdiction, program: protocolDefinition.program, protocol: protocolDefinition.id }),
        currentProjectId ? getSurveyDesignAssets({ project_id: currentProjectId, site_id: currentSiteId, program: protocolDefinition.program, submodule: protocolDefinition.program === 'terrestrial_vertebrates' ? activeVertebrateSubmoduleId : '', protocol: protocolDefinition.id }) : Promise.resolve({ design_assets: [] }),
      ])
      setSurveyState((current) => mergeSyncPull(current, { ...pulled, protocols: toArray(protocolResponse?.protocols), taxonomy_packages: toArray(taxonomyResponse?.packages), design_assets: [...toArray(pulled?.design_assets), ...toArray(designAssetResponse?.design_assets)], active_program: protocolDefinition.program, active_protocol: protocolDefinition.id, active_vertebrate_submodule: protocolDefinition.program === 'terrestrial_vertebrates' ? activeVertebrateSubmoduleId : '', active_jurisdiction: exportJurisdiction }))
    } catch (err) { setError(getApiErrorMessage(err, 'Unable to pull survey data.')) }
    finally { setLoadingSync(false) }
  }

  function handleSelectRoute(routeId) {
    setSurveyState((current) => ({ ...current, activeRouteId: routeId }))
    setTransectSession((current) => { if (!current.started_at) return { ...current, route_id: routeId }; if (current.route_id === routeId) return current; return createEmptyTransectSession(transectForm.observer || observationForm.observer || '') })
  }

  function handleSelectProgram(programId) {
    const nextSubmoduleId = programId === 'terrestrial_vertebrates' ? deriveVertebrateSubmoduleId(surveyState.activeVertebrateSubmodule, observationForm.taxon_group, protocolState.protocol) : ''
    const nextProtocol = protocolCatalog.find((item) => item.program === programId && (programId !== 'terrestrial_vertebrates' || toArray(item.vertebrateSubmodules).length === 0 || toArray(item.vertebrateSubmodules).includes(nextSubmoduleId))) || protocolCatalog.find((item) => item.program === programId) || protocolCatalog[0] || PROTOCOL_OPTIONS[0]
    setProtocolState(createProtocolState(nextProtocol.id, protocolCatalog))
    onSelectModule?.(programId)
    setObservationForm((current) => ({ ...current, taxon_group: programId === 'terrestrial_vertebrates' ? (getVertebrateSubmoduleById(nextSubmoduleId).taxonGroup || nextProtocol.defaultTaxonGroup) : nextProtocol.defaultTaxonGroup, evidence_type: nextProtocol.defaultEvidenceType }))
    setSurveyState((current) => ({ ...current, activeVertebrateSubmodule: programId === 'terrestrial_vertebrates' ? nextSubmoduleId : current.activeVertebrateSubmodule }))
  }

  function handleSelectProtocol(protocolId) {
    const nextProtocol = getProtocolDefinition(protocolId, protocolCatalog)
    setProtocolState(createProtocolState(nextProtocol.id, protocolCatalog))
    setObservationForm((current) => ({ ...current, taxon_group: currentProgram === 'terrestrial_vertebrates' ? (activeVertebrateSubmodule?.taxonGroup || nextProtocol.defaultTaxonGroup) : nextProtocol.defaultTaxonGroup, evidence_type: nextProtocol.defaultEvidenceType }))
  }

  function handleSelectVertebrateSubmodule(submoduleId) {
    const nextSubmodule = getVertebrateSubmoduleById(submoduleId)
    const nextProtocol = protocolCatalog.find((item) => item.program === 'terrestrial_vertebrates' && (toArray(item.vertebrateSubmodules).length === 0 || toArray(item.vertebrateSubmodules).includes(nextSubmodule.id))) || protocolDefinition
    setSurveyState((current) => ({ ...current, activeVertebrateSubmodule: nextSubmodule.id }))
    if (nextProtocol?.id && nextProtocol.id !== protocolDefinition.id) setProtocolState(createProtocolState(nextProtocol.id, protocolCatalog))
    setObservationForm((current) => ({ ...current, taxon_group: nextSubmodule.taxonGroup, evidence_type: nextProtocol?.defaultEvidenceType || current.evidence_type }))
  }

  function handleProtocolEventFieldChange(fieldKey, value) { setProtocolState((current) => ({ ...current, event: { ...current.event, [fieldKey]: value } })) }
  function handleProtocolRecordFieldChange(fieldKey, value) { setProtocolState((current) => ({ ...current, record: { ...current.record, [fieldKey]: value } })) }

  async function handlePushSync() {
    if (!isOnline || surveyState.syncQueue.length === 0) return
    setLoadingSync(true); setError(null)
    try {
      const response = await pushSurveySync({ device_id: surveyState.syncMeta?.deviceId || 'field-device-web', user_id: 'field-user-web', operations: surveyState.syncQueue.map((op) => ({ entity_type: op.entity_type, operation: op.operation, entity_id: op.entity_id, payload: op.payload })) })
      setSurveyState(applySyncResult(surveyState, response.sync_job))
      const pulled = await pullSurveySync('')
      setSurveyState((current) => mergeSyncPull(current, pulled))
    } catch (err) {
      setError(getApiErrorMessage(err, 'Unable to push queued field data.'))
      setSurveyState((current) => ({ ...current, syncMeta: { ...(current.syncMeta || {}), lastStatus: 'error', lastError: getApiErrorMessage(err, 'Unable to push queued field data.') } }))
    } finally { setLoadingSync(false) }
  }

  async function submitProjectOnlineAware() {
    const name = projectForm.name.trim() || `${platformConfig?.target_species?.common_name_zh || '外业'}项目`
    const payload = { name, region: projectForm.region.trim() || platformConfig?.study_region?.name_zh || platformConfig?.study_region?.name || '', team_members: [], target_taxa: TAXA, notes: '' }
    try {
      if (isOnline) { const response = await createSurveyProject(payload); setSurveyState((current) => replaceEntity(current, 'project', response.project, { select: true })) }
      else { setSurveyState((current) => upsertLocalEntity(current, 'project', payload)) }
      setProjectForm({ name: '', region: '' })
    } catch (err) { setSurveyState((current) => upsertLocalEntity(current, 'project', payload)); setProjectForm({ name: '', region: '' }); setError(getApiErrorMessage(err, 'Project saved locally and queued for sync.')) }
  }

  async function saveSiteOnlineAware() {
    if (!currentProjectId) return
    const latitude = siteForm.latitude ? Number(siteForm.latitude) : currentPosition?.lat
    const longitude = siteForm.longitude ? Number(siteForm.longitude) : currentPosition?.lon
    const payload = { project_id: currentProjectId, name: siteForm.name.trim() || `Site ${projectSites.length + 1}`, habitat_type: siteForm.habitat_type.trim(), latitude, longitude, admin_region: currentProject?.region || '' }
    try {
      if (isOnline) { const response = await createFieldSurveySite(payload); setSurveyState((current) => replaceEntity(current, 'site', response.site, { select: true })) }
      else { setSurveyState((current) => upsertLocalEntity(current, 'site', payload)) }
      setSiteForm({ name: '', habitat_type: '', latitude: '', longitude: '' })
    } catch (err) { setSurveyState((current) => upsertLocalEntity(current, 'site', payload)); setSiteForm({ name: '', habitat_type: '', latitude: '', longitude: '' }); setError(getApiErrorMessage(err, 'Site saved locally and queued for sync.')) }
  }

  async function handleImportRoute(event) {
    const file = event.target.files?.[0]
    if (!file || !currentProjectId) return
    setImportingRoute(true); setError(null)
    try {
      if (isOnline) {
        const response = await importSurveyRoute(file, { projectId: currentProjectId, siteId: currentSiteId, name: file.name.replace(/\.[^.]+$/, ''), routeType: protocolDefinition.requiresAsset ? 'transect' : 'station' })
        const routePayload = { ...response.route, extra: { ...(response.route?.extra || {}), ...buildProtocolExtra('event') }, sync_state: 'synced', server_updated_at: response.route.updated_at }
        setSurveyState((current) => ({ ...current, activeRouteId: routePayload.route_id, routes: [...current.routes.filter((item) => item.route_id !== routePayload.route_id), routePayload].sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || '')) }))
      } else {
        const parsed = await parseRouteFile(file)
        setSurveyState((current) => upsertLocalEntity(current, 'route', { project_id: currentProjectId, site_id: currentSiteId, route_type: protocolDefinition.requiresAsset ? 'transect' : 'station', ...parsed, extra: buildProtocolExtra('event') }, { operation: 'upsert', select: true }))
      }
    } catch (err) { setError(getApiErrorMessage(err, 'Unable to import the selected route file.')) }
    finally { event.target.value = ''; setImportingRoute(false) }
  }

  async function preloadTilesOnlineAware() {
    setDownloadingTiles(true); setError(null)
    try {
      const bbox = platformConfig?.study_region?.bounding_box || { min_lat: mapCenter[0] - 0.2, max_lat: mapCenter[0] + 0.2, min_lon: mapCenter[1] - 0.2, max_lon: mapCenter[1] + 0.2 }
      const minZoom = 8; const maxZoom = Math.min(14, platformConfig?.map?.max_zoom || 14)
      const cached = await prefetchMapTiles({ tileUrl, bbox, minZoom, maxZoom, cacheKey: currentProjectId || 'default' })
      const payload = { project_id: currentProjectId, name: `${currentProject?.name || 'Survey'} tiles`, bbox, min_zoom: minZoom, max_zoom: maxZoom, tile_url: tileUrl, tile_count_estimate: cached.total, storage_bytes_estimate: cached.downloaded * 18000, status: cached.downloaded > 0 ? 'cached' : 'planned', extra: { capped: cached.capped, downloaded_tiles: cached.downloaded } }
      if (isOnline) { try { const response = await createOfflineMapPackage(payload); setSurveyState((current) => replaceEntity(current, 'map_package', response.package)) } catch (err) { setSurveyState((current) => upsertLocalEntity(current, 'map_package', payload)); setError(getApiErrorMessage(err, 'Offline map package saved locally and queued for sync.')) } }
      else { setSurveyState((current) => upsertLocalEntity(current, 'map_package', payload)) }
    } catch (err) { setError(getApiErrorMessage(err, 'Unable to cache offline tiles for this project area.')) }
    finally { setDownloadingTiles(false) }
  }

  async function handleAddAttachments(event) {
    const files = Array.from(event.target.files || [])
    if (files.length === 0) return
    setSerializingMedia(true); setError(null)
    try { const serialized = []; for (const file of files) serialized.push(await serializeAttachment(file)); appendDraftAttachments(serialized) }
    catch (err) { setError(getApiErrorMessage(err, 'Unable to store attachments locally.')) }
    finally { event.target.value = ''; setSerializingMedia(false) }
  }

  async function handleCapturePhoto() {
    if (!nativeMobile) return
    setSerializingMedia(true); setError(null)
    try { const attachment = await capturePhotoAttachment(CameraSource.Camera); if (!attachment) return; await pulseFeedback(ImpactStyle.Light); appendDraftAttachments([attachment]) }
    catch (err) { setError(getApiErrorMessage(err, 'Unable to capture a field photo on this device.')) }
    finally { setSerializingMedia(false) }
  }

  async function handleStartAudioCapture() {
    if (typeof window === 'undefined' || !navigator?.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') { setError('Audio recording is not supported in this browser or device.'); return }
    if (audioCaptureStatus === 'recording') return
    setSerializingMedia(true); setError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mimeType = MediaRecorder.isTypeSupported?.('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : ''
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
      audioChunksRef.current = []; audioStreamRef.current = stream; audioRecorderRef.current = recorder
      recorder.ondataavailable = (event) => { if (event.data && event.data.size > 0) audioChunksRef.current.push(event.data) }
      recorder.onstop = async () => {
        try {
          const blob = new Blob(audioChunksRef.current, { type: recorder.mimeType || 'audio/webm' })
          if (blob.size > 0) { const extension = blob.type.includes('ogg') ? 'ogg' : 'webm'; const file = new File([blob], `field-audio-${Date.now()}.${extension}`, { type: blob.type || 'audio/webm' }); const attachment = await serializeAttachment(file); appendDraftAttachments([attachment]); setObservationForm((current) => ({ ...current, evidence_type: 'audio' })); await pulseFeedback(ImpactStyle.Light) }
        } catch (err) { setError(getApiErrorMessage(err, 'Unable to save the recorded audio evidence.')) }
        finally { if (audioStreamRef.current) { audioStreamRef.current.getTracks().forEach((track) => track.stop()); audioStreamRef.current = null }; audioRecorderRef.current = null; audioChunksRef.current = []; setAudioCaptureStatus('idle'); setSerializingMedia(false) }
      }
      recorder.start(); setObservationForm((current) => ({ ...current, evidence_type: 'audio' })); setAudioCaptureStatus('recording'); await pulseFeedback(ImpactStyle.Light)
    } catch (err) { setSerializingMedia(false); setAudioCaptureStatus('idle'); setError(getApiErrorMessage(err, 'Unable to start audio recording on this device.')) }
  }

  async function handleStopAudioCapture() {
    if (!audioRecorderRef.current || audioRecorderRef.current.state === 'inactive') return
    try { audioRecorderRef.current.stop() } catch (err) { setSerializingMedia(false); setAudioCaptureStatus('idle'); setError(getApiErrorMessage(err, 'Unable to stop audio recording cleanly.')) }
  }

  async function useCurrentGps() {
    if (nativeMobile) {
      try { const position = await requestNativeCurrentPosition(); if (!position) return; setCurrentPosition(position); setSiteForm((current) => ({ ...current, latitude: String(position.lat.toFixed(6)), longitude: String(position.lon.toFixed(6)) })); await pulseFeedback(ImpactStyle.Light) }
      catch (err) { setError(getApiErrorMessage(err, 'Unable to use the device GPS right now.')) }
      return
    }
    if (!currentPosition) return
    setSiteForm((current) => ({ ...current, latitude: String(currentPosition.lat.toFixed(6)), longitude: String(currentPosition.lon.toFixed(6)) }))
  }

  function buildEventGeometry() {
    if (selectedRoute?.geometry) return selectedRoute.geometry
    if (currentSite?.latitude != null && currentSite?.longitude != null) return { type: 'Point', coordinates: [currentSite.longitude, currentSite.latitude] }
    if (currentPosition?.lat != null && currentPosition?.lon != null) return { type: 'Point', coordinates: [currentPosition.lon, currentPosition.lat] }
    return null
  }

  function buildProtocolExtra(kind = 'event', options = {}) {
    const eventPayload = options.eventPayload || eventPayloadDraft
    const activeSubmodule = currentProgram === 'terrestrial_vertebrates' ? activeVertebrateSubmoduleId : (protocolDefinition.defaultTaxonGroup || '')
    const extra = { program: protocolDefinition.program, submodule: activeSubmodule, protocol: protocolDefinition.id, protocol_label: protocolDefinition.label, asset_label: protocolDefinition.assetLabel, jurisdiction: exportJurisdiction, event_fields: eventPayload, event_payload: eventPayload }
    if (kind === 'record') { extra.record_fields = options.recordPayload || normalizeProtocolFieldValues(protocolDefinition.recordFields, protocolState.record); extra.record_payload = options.recordPayload || normalizeProtocolFieldValues(protocolDefinition.recordFields, protocolState.record); if (options.eventId) extra.event_id = options.eventId }
    return extra
  }

  function buildSamplingEventRequest(eventId = '') {
    const startedAt = transectSession.started_at || new Date().toISOString()
    const endedAt = transectSession.ended_at || ''
    const observers = splitObserverNames(transectForm.observer, observationForm.observer)
    const activeSubmodule = currentProgram === 'terrestrial_vertebrates' ? activeVertebrateSubmoduleId : (protocolDefinition.defaultTaxonGroup || '')
    const effortMetrics = { observer_count: Number(protocolState.event.observer_count || 0) || observers.length || 0, observation_count: protocolObservations.length, track_count: protocolTracks.length, duration_min: transectEffortMinutes || Number(protocolState.event.duration_min || protocolState.event.point_duration_min || 0) || 0 }
    if (selectedRouteLength > 0) effortMetrics.route_length_m = selectedRouteLength
    if (protocolDefinition.supportsTrack && trackInfo.distance_m > 0) effortMetrics.distance_walked_m = Math.round(trackInfo.distance_m)
    return { event_id: eventId || surveyState.activeEventId || `event-${Date.now()}`, project_id: currentProjectId, site_id: currentSiteId, route_id: selectedRoute?.route_id || '', design_asset_id: surveyState.activeDesignAssetId || '', program: protocolDefinition.program, submodule: activeSubmodule, protocol: protocolDefinition.id, jurisdiction: exportJurisdiction, started_at: startedAt, ended_at: endedAt, geometry: buildEventGeometry(), weather: { summary: transectForm.weather.trim() }, effort_metrics: effortMetrics, event_payload: eventPayloadDraft, observers, team: [], notes: transectForm.notes.trim(), sync_state: isOnline ? 'synced' : 'queued', extra: { ...buildProtocolExtra('event', { eventPayload: eventPayloadDraft }), route_id: selectedRoute?.route_id || '' } }
  }

  function buildObservationRecordPayload({ matched, observedAt, linkedEventId = '' }) {
    const payload = normalizeProtocolFieldValues(protocolDefinition.recordFields, protocolState.record)
    if (matched?.internal_taxon_id || matched?.taxon_id || matched?.species_id) payload.taxon_id = matched.internal_taxon_id || matched.taxon_id || matched.species_id
    payload.count = Number(observationForm.count || 1)
    payload.observation_time = observedAt
    if (protocolDefinition.id === 'herp_infrared_camera') payload.evidence_type = observationForm.evidence_type
    else if (!payload.detection_type) payload.detection_type = observationForm.evidence_type
    if (!payload.behavior && observationForm.behavior.trim()) payload.behavior = observationForm.behavior.trim()
    if (linkedEventId) payload.event_id = linkedEventId
    if (currentProgram === 'terrestrial_vertebrates' && activeVertebrateSubmoduleId) payload.submodule = activeVertebrateSubmoduleId
    return payload
  }

  function buildObservationMediaPayload(linkedEventId = '') {
    const activeSubmodule = currentProgram === 'terrestrial_vertebrates' ? activeVertebrateSubmoduleId : (protocolDefinition.defaultTaxonGroup || '')
    const attachmentIds = normalizeAttachmentIds(attachments.map((item) => item?.attachment_id || item?.media_id))
    return applyAttachmentContext(attachments, attachmentIds, { owner_type: linkedEventId ? 'event' : 'draft', owner_id: linkedEventId || surveyState.activeDesignAssetId || selectedRoute?.route_id || currentSiteId || currentProjectId || '', event_id: linkedEventId, sync_state: 'local_only' }).map((item) => ({ ...item, program: protocolDefinition.program, submodule: activeSubmodule, protocol: protocolDefinition.id, jurisdiction: exportJurisdiction }))
  }

  async function saveReviewEventOnlineAware({ quiet = false } = {}) {
    if (!currentProjectId) return null
    if (eventValidationMissing.length > 0) { setError(`Complete these ${protocolDefinition.label} event fields before saving or exporting: ${eventValidationMissing.join(', ')}`); return null }
    const payload = buildSamplingEventRequest()
    const latestComparable = latestProtocolEvent ? JSON.stringify({ protocol: latestProtocolEvent.protocol, submodule: latestProtocolEvent.submodule || latestProtocolEvent.extra?.submodule || '', jurisdiction: latestProtocolEvent.jurisdiction, route_id: latestProtocolEvent.route_id, event_payload: latestProtocolEvent.event_payload || latestProtocolEvent.extra?.event_payload || {}, notes: latestProtocolEvent.notes || '' }) : ''
    const draftComparable = JSON.stringify({ protocol: payload.protocol, submodule: payload.submodule || '', jurisdiction: payload.jurisdiction, route_id: payload.route_id, event_payload: payload.event_payload, notes: payload.notes })
    if (latestProtocolEvent && latestComparable === draftComparable) return latestProtocolEvent
    setSavingReviewEvent(true); setError(null)
    try {
      if (isOnline) { const response = await createSurveyEvent(payload); setSurveyState((current) => replaceEntity(current, 'event', response.event, { select: true })); if (!quiet) setVertebrateExportResult((current) => ({ ...(current || {}), latestEvent: response.event })); return response.event }
      setSurveyState((current) => upsertLocalEntity(current, 'event', payload, { select: true })); if (!quiet) setVertebrateExportResult((current) => ({ ...(current || {}), latestEvent: payload })); return payload
    } catch (err) { setSurveyState((current) => upsertLocalEntity(current, 'event', payload, { select: true })); setError(getApiErrorMessage(err, 'Event saved locally and queued for sync.')); return payload }
    finally { setSavingReviewEvent(false) }
  }

  async function handleCreateProtocolExport(jurisdiction, { requireMaskPreview = false } = {}) {
    if (!isOnline || !currentProjectId) return null
    if (protocolObservations.length === 0) { setError(`Save at least one ${protocolDefinition.label.toLowerCase()} observation before exporting.`); return null }
    const exportTaxonomyPackageStatus = taxonomyGateByJurisdiction[jurisdiction] || deriveSurveyTaxonomyPackageStatus([])
    const exportJurisdictionLabel = EXPORT_JURISDICTIONS.find((item) => item.id === jurisdiction)?.label || jurisdiction
    if (exportTaxonomyPackageStatus.isBlocked) { setError(buildTaxonomyGateBlockingMessage(exportTaxonomyPackageStatus, protocolDefinition, exportJurisdictionLabel)); return null }
    setExportingVertebrateJurisdiction(jurisdiction); setError(null)
    try {
      const eventRecord = await saveReviewEventOnlineAware({ quiet: requireMaskPreview })
      const response = await createSurveyExportJob(jurisdiction, { project_id: currentProjectId, site_id: currentSiteId, program: protocolDefinition.program, submodule: protocolDefinition.program === 'terrestrial_vertebrates' ? activeVertebrateSubmoduleId : '', protocol: protocolDefinition.id, event_id: eventRecord?.event_id || latestProtocolEvent?.event_id || '', format: 'csv', extra: { route_id: selectedRoute?.route_id || '', design_asset_id: surveyState.activeDesignAssetId || '', submodule: protocolDefinition.program === 'terrestrial_vertebrates' ? activeVertebrateSubmoduleId : '' } })
      const exportJob = response.export_job || response
      setSurveyState((current) => replaceEntity(current, 'export_job', exportJob))
      toArray(exportJob?.bundle?.files).forEach((file) => { if (!file?.content) return; downloadTextFile(file.filename || `${protocolDefinition.id}-${file.output_id || 'export'}.csv`, file.content, file.media_type || 'text/csv;charset=utf-8') })
      return { eventRecord, exportJob, summary: response.summary || exportJob.summary || {} }
    } catch (err) { setError(getApiErrorMessage(err, `Unable to export the ${jurisdiction.replace(/_/g, ' ')} ${protocolDefinition.label.toLowerCase()} bundle.`)); return null }
    finally { setExportingVertebrateJurisdiction('') }
  }

  async function handleCreateVertebrateExport(jurisdiction) {
    if (!isTerrestrialVertebrateProtocol) return
    const result = await handleCreateProtocolExport(jurisdiction, { requireMaskPreview: true })
    if (result) setVertebrateExportResult({ jurisdiction, exportJob: result.exportJob, summary: result.summary })
  }

  async function saveObservationOnlineAware() {
    if (!currentProjectId || (protocolDefinition.requiresAsset && !selectedRoute)) return
    const eventRecord = await saveReviewEventOnlineAware({ quiet: true })
    if (!eventRecord?.event_id) return
    const matched = findSpeciesMatch(taxonomyCatalog, observationForm.species_text)
    const observedAt = new Date().toISOString()
    const linkedEventId = eventRecord.event_id
    const recordPayload = buildObservationRecordPayload({ matched, observedAt, linkedEventId })
    const latitude = currentPosition?.lat ?? currentSite?.latitude ?? null
    const longitude = currentPosition?.lon ?? currentSite?.longitude ?? null
    const snapped = latitude != null && longitude != null ? snapObservationToRoutes([longitude, latitude], siteRoutes) : { snapped_route_id: '', snapped_distance_m: 0 }
    const payload = { project_id: currentProjectId, site_id: currentSiteId, route_id: selectedRoute?.route_id || snapped.snapped_route_id || '', event_id: linkedEventId, program: protocolDefinition.program, submodule: currentProgram === 'terrestrial_vertebrates' ? activeVertebrateSubmoduleId : (protocolDefinition.defaultTaxonGroup || ''), protocol: protocolDefinition.id, jurisdiction: exportJurisdiction, scientific_name: matched?.scientific || matched?.scientific_name || (observationForm.unknown_taxon ? '' : observationForm.species_text.trim()), chinese_name: matched?.chinese || matched?.chinese_name || '', english_name: matched?.english || matched?.english_name || '', taxon_group: observationForm.taxon_group, count: Number(observationForm.count || 1), evidence_type: observationForm.evidence_type, behavior: observationForm.behavior.trim(), habitat_notes: observationForm.habitat_notes.trim(), confidence: Number(observationForm.confidence || 0.5), observer: observationForm.observer.trim(), unknown_taxon: observationForm.unknown_taxon, trace_only: observationForm.trace_only, latitude, longitude, geometry: latitude != null && longitude != null ? { type: 'Point', coordinates: [longitude, latitude] } : null, media: buildObservationMediaPayload(linkedEventId), observed_at: observedAt, snapped_route_id: snapped.snapped_route_id || selectedRoute?.route_id || '', snapped_distance_m: snapped.snapped_distance_m, transect_observer: transectSession.observer || transectForm.observer.trim(), transect_weather: transectSession.weather || transectForm.weather.trim(), transect_notes: transectSession.notes || transectForm.notes.trim(), transect_started_at: transectSession.started_at || '', ai_suggestion: matched ? { scientific_name: matched.scientific || matched.scientific_name || '', chinese_name: matched.chinese || matched.chinese_name || '', english_name: matched.english || matched.english_name || '' } : {}, record_payload: recordPayload, extra: buildProtocolExtra('record', { recordPayload, eventId: linkedEventId }) }
    const resetForm = () => { setObservationForm({ species_text: '', taxon_group: observationForm.taxon_group, count: 1, evidence_type: observationForm.evidence_type, confidence: observationForm.confidence, observer: observationForm.observer, behavior: '', habitat_notes: '', unknown_taxon: false, trace_only: false }); setProtocolState((current) => ({ ...current, record: buildProtocolFieldState(protocolDefinition.recordFields) })); replaceDraftAttachments([]) }
    try { if (isOnline) { const response = await createSurveyObservation(payload); setSurveyState((current) => replaceEntity(current, 'observation', response.observation)) } else { setSurveyState((current) => upsertLocalEntity(current, 'observation', payload)) }; resetForm() }
    catch (err) { setSurveyState((current) => upsertLocalEntity(current, 'observation', payload)); resetForm(); setError(getApiErrorMessage(err, 'Observation saved locally and queued for sync.')) }
  }

  function handleStartTrack() {
    if (!protocolDefinition.supportsTrack) { setError(`${protocolDefinition.label} uses a station or plot workflow, so live track recording is disabled.`); return }
    if (!selectedRoute) { setError(`Select or import a ${protocolDefinition.assetLabel.toLowerCase()} before starting a walk.`); return }
    if (!nativeMobile && !navigator?.geolocation) { setError('Geolocation is not available in this browser.'); return }
    if (watchRef.current) return
    setStoredTrackDraft(buildTrackDraftForStart({ existingDraft: surveyState.activeTrackDraft, selectedRoute, observer: transectForm.observer, weather: transectForm.weather, notes: transectForm.notes, extra: buildProtocolExtra('event'), startedAt: new Date().toISOString() }))
  }

  async function stopTrackOnlineAware() {
    await clearTrackWatch()
    const draft = normalizeTrackDraft(trackDraftRef.current)
    if (!draft) { setSurveyState((current) => ({ ...current, activeTrackDraft: null })); syncDraftIntoUi(null); return }
    const endedAt = new Date().toISOString()
    if (draft.points.length > 1 && currentProjectId) {
      const eventRecord = await saveReviewEventOnlineAware({ quiet: true })
      if (!eventRecord?.event_id) return
      const payload = { project_id: currentProjectId, site_id: currentSiteId, route_id: draft.route_id || selectedRoute?.route_id || '', event_id: eventRecord.event_id, program: protocolDefinition.program, submodule: currentProgram === 'terrestrial_vertebrates' ? activeVertebrateSubmoduleId : (protocolDefinition.defaultTaxonGroup || ''), protocol: protocolDefinition.id, jurisdiction: exportJurisdiction, name: `${draft.route_name || selectedRoute?.name || currentSite?.name || currentProject?.name || 'Survey'} ${new Date().toLocaleTimeString()}`, source: 'recorded', geometry: { type: 'LineString', coordinates: draft.points }, point_times: draft.point_times, started_at: draft.started_at, ended_at: endedAt, distance_m: lineDistanceMeters(draft.points), observer: draft.observer || '', weather: draft.weather || '', notes: draft.notes || '', extra: draft.extra || buildProtocolExtra('event') }
      try { if (isOnline) { const response = await createSurveyTrack(payload); setSurveyState((current) => replaceEntity(current, 'track', response.track)) } else { setSurveyState((current) => upsertLocalEntity(current, 'track', payload)) } }
      catch (err) { setSurveyState((current) => upsertLocalEntity(current, 'track', payload)); setError(getApiErrorMessage(err, 'Track saved locally and queued for sync.')) }
    }
    setSurveyState((current) => ({ ...current, activeTrackDraft: null }))
    setTransectSession((current) => current.started_at ? { ...current, ended_at: current.ended_at || endedAt } : current)
    syncDraftIntoUi(null)
  }

  function exportRoute(record, format) {
    if (!record) return
    if (format === 'gpx') { downloadTextFile(`${record.name || 'route'}.gpx`, buildGpx(record), 'application/gpx+xml;charset=utf-8'); return }
    downloadTextFile(`${record.name || 'route'}.geojson`, JSON.stringify(buildFeatureCollection(record), null, 2), 'application/geo+json;charset=utf-8')
  }

  async function handleExportRouteReport(format) {
    if (!selectedRoute?.route_id || !isOnline) return
    if (activeTaxonomyPackageStatus.isBlocked) { setError(buildTaxonomyGateBlockingMessage(activeTaxonomyPackageStatus, protocolDefinition, activeJurisdictionLabel)); return }
    setExportingRouteReportFormat(format); setError(null)
    try { const exported = await exportSurveyRouteReport(selectedRoute.route_id, format); downloadBlobFile(exported.blob, exported.filename || `${selectedRoute.name || 'route-report'}.${format}`) }
    catch (err) { setError(getApiErrorMessage(err, `Unable to export the ${format.toUpperCase()} route or station report.`)) }
    finally { setExportingRouteReportFormat('') }
  }

  // ── Render ──
  return (
    <div className="space-y-6">
      <HeaderPanel
        copy={copy}
        isOnline={isOnline}
        loadingSync={loadingSync}
        syncQueueLength={surveyState.syncQueue.length}
        onPull={handlePullSync}
        onPush={handlePushSync}
      />

      <ProtocolPanel
        copy={copy}
        locale={locale}
        currentProgram={currentProgram}
        activeModuleMeta={activeModuleMeta}
        moduleLabel={moduleLabel}
        moduleDescription={moduleDescription}
        moduleShellHint={moduleShellHint}
        moduleProtocols={moduleProtocols}
        ActiveModuleIcon={ActiveModuleIcon}
        protocolDefinition={protocolDefinition}
        visibleProtocols={visibleProtocols}
        activeVertebrateSubmoduleId={activeVertebrateSubmoduleId}
        activeVertebrateSubmodule={activeVertebrateSubmodule}
        activeJurisdictionLabel={activeJurisdictionLabel}
        exportJurisdiction={exportJurisdiction}
        activeTaxonomyPackage={activeTaxonomyPackage}
        taxonomyPackageNote={taxonomyPackageNote}
        activeDesignAssets={activeDesignAssets}
        protocolCount={toArray(surveyState.protocols).length}
        onSelectProgram={handleSelectProgram}
        onSelectProtocol={handleSelectProtocol}
        onSelectVertebrateSubmodule={handleSelectVertebrateSubmodule}
        onChangeJurisdiction={setExportJurisdiction}
      />

      <PilotFlowPanel
        copy={copy}
        selectedRoute={selectedRoute}
        pilotStatusCards={pilotStatusCards}
        workflowSteps={workflowSteps}
        protocolDefinition={protocolDefinition}
      />

      <StatusBanner tone="error" message={error} />
      <StatusBanner tone="warning" message={taxonomyGateWarningMessage} />

      <EssentialWorkflowPanel
        copy={copy}
        mapCenter={mapCenter}
        tileUrl={tileUrl}
        tileAttribution={tileAttribution}
        projectSites={projectSites}
        selectedRoute={selectedRoute}
        siteRoutes={siteRoutes}
        routeObservations={routeObservations}
        routeTracks={routeTracks}
        liveTrack={liveTrack}
        trackInfo={trackInfo}
        trackStatus={trackStatus}
        protocolDefinition={protocolDefinition}
        hasActiveTrackDraft={hasActiveTrackDraft}
        currentProjectId={currentProjectId}
        onStartTrack={handleStartTrack}
        onStopTrack={stopTrackOnlineAware}
        onSaveObservation={saveObservationOnlineAware}
      />

      <section className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
        <div className="space-y-4">
          <ProjectManagementPanel
            copy={copy}
            surveyState={surveyState}
            currentProjectId={currentProjectId}
            currentSiteId={currentSiteId}
            projectSites={projectSites}
            projectForm={projectForm}
            siteForm={siteForm}
            onSetProjectForm={setProjectForm}
            onSetSiteForm={setSiteForm}
            onSelectProject={(value) => setSurveyState((current) => ({ ...current, activeProjectId: value, activeSiteId: '', activeRouteId: '', activeEventId: '' }))}
            onSelectSite={(value) => setSurveyState((current) => ({ ...current, activeSiteId: value, activeRouteId: '', activeEventId: '' }))}
            onCreateProject={submitProjectOnlineAware}
            onSaveSite={saveSiteOnlineAware}
            onUseGps={useCurrentGps}
          />

          <SurveyEventPanel
            copy={copy}
            protocolDefinition={protocolDefinition}
            protocolState={protocolState}
            siteRoutes={siteRoutes}
            currentRouteId={currentRouteId}
            selectedRoute={selectedRoute}
            routeObservations={routeObservations}
            protocolTracks={protocolTracks}
            protocolObservations={protocolObservations}
            transectForm={transectForm}
            transectSession={transectSession}
            transectEffortMinutes={transectEffortMinutes}
            trackStatus={trackStatus}
            onSelectRoute={handleSelectRoute}
            onSetTransectForm={setTransectForm}
            onProtocolEventFieldChange={handleProtocolEventFieldChange}
          />

          {isTerrestrialVertebrateProtocol && (
            <VertebrateReviewPanel
              protocolDefinition={protocolDefinition}
              exportJurisdiction={exportJurisdiction}
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

          <OfflineMapPanel
            copy={copy}
            selectedRoute={selectedRoute}
            activeMapPackages={activeMapPackages}
            currentProjectId={currentProjectId}
            downloadingTiles={downloadingTiles}
            importingRoute={importingRoute}
            onPreloadTiles={preloadTilesOnlineAware}
            onImportRoute={handleImportRoute}
            onExportRoute={exportRoute}
          />
        </div>

        <div className="section-shell">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-white">{copy.map}</h3>
              <p className="text-xs text-gray-500">{selectedRoute?.name || currentProject?.name || 'Field map'}</p>
            </div>
            <div className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-gray-300">
              {siteRoutes.length} routes / {protocolObservations.length} protocol records
            </div>
          </div>
          <FieldSurveyMap
            center={mapCenter}
            tileUrl={tileUrl}
            attribution={tileAttribution}
            sites={projectSites}
            routes={selectedRoute ? [selectedRoute] : siteRoutes}
            observations={routeObservations}
            tracks={routeTracks}
            liveTrack={liveTrack}
          />
          {routeComparison && (
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <MetricCard title={copy.routeSummary} value={`${Math.round(routeComparison.planned_m)} m`} note="planned" />
              <MetricCard title={copy.routeSummary} value={`${Math.round(routeComparison.walked_m)} m`} note="walked" />
            </div>
          )}
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
        <ObservationFormPanel
          copy={copy}
          protocolDefinition={protocolDefinition}
          protocolState={protocolState}
          observationForm={observationForm}
          attachments={attachments}
          speciesSuggestions={speciesSuggestions}
          taxonomyCatalog={taxonomyCatalog}
          availableTaxaOptions={availableTaxaOptions}
          selectedRoute={selectedRoute}
          routeObservations={routeObservations}
          currentProjectId={currentProjectId}
          nativeMobile={nativeMobile}
          serializingMedia={serializingMedia}
          audioCaptureStatus={audioCaptureStatus}
          onSetObservationForm={setObservationForm}
          onProtocolRecordFieldChange={handleProtocolRecordFieldChange}
          onSaveObservation={saveObservationOnlineAware}
          onAddAttachments={handleAddAttachments}
          onStartAudioCapture={handleStartAudioCapture}
          onStopAudioCapture={handleStopAudioCapture}
          onCapturePhoto={handleCapturePhoto}
        />

        <div className="space-y-4">
          <TrackingPanel
            copy={copy}
            trackStatus={trackStatus}
            trackInfo={trackInfo}
            selectedRoute={selectedRoute}
            latestTrack={latestTrack}
            protocolDefinition={protocolDefinition}
            hasActiveTrackDraft={hasActiveTrackDraft}
            onStartTrack={handleStartTrack}
            onStopTrack={stopTrackOnlineAware}
          />
          <MediaPanel copy={copy} mediaInbox={surveyState.mediaInbox} />
          <SyncStatusPanel copy={copy} surveyState={surveyState} />
        </div>
      </section>
    </div>
  )
}
