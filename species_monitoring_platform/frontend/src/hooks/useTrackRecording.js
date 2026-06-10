import { useRef, useState } from 'react'
import {
  createEmptyTrackDraft,
  normalizeTrackDraft,
} from '../lib/fieldOpsDrafts'
import {
  haversineMeters,
  lineDistanceMeters,
} from '../lib/surveyOffline'
import {
  stopNativePositionWatch,
} from '../lib/mobileNative'

/**
 * Pure denoising decision used by `handleTrackPoint`. Exported so it can be
 * unit-tested without spinning up a React renderer. Three independent gates:
 *
 *   1. `maxAccuracy`  — drop fixes whose reported accuracy is worse than the
 *                       threshold (default 30 m). Set to `Infinity` to disable.
 *   2. `minInterval`  — drop fixes that arrive sooner than `minInterval` ms
 *                       after the previously accepted fix (default 3000 ms).
 *   3. `minDistanceM` — drop fixes closer than `minDistanceM` to the previously
 *                       accepted point (default 5 m). Set to 0 to disable.
 *
 * Returns `{ accept: true }` on success, or `{ accept: false, reason }` with a
 * human-readable hint shown in the track status panel.
 *
 * @param {{ lat: number, lon: number, accuracy?: number, timestamp?: number }} position
 * @param {{ lastPoint: [number, number] | null, lastTimeMs: number, now?: number }} state
 * @param {{ maxAccuracy?: number, minInterval?: number, minDistanceM?: number }} [options]
 */
export function decideTrackPointAcceptance(position, state, options = {}) {
  const { maxAccuracy = 30, minInterval = 3000, minDistanceM = 5 } = options
  const now = state?.now ?? Date.now()
  if (
    position?.accuracy != null &&
    Number.isFinite(position.accuracy) &&
    position.accuracy > maxAccuracy
  ) {
    return {
      accept: false,
      reason: `GPS accuracy ${Math.round(position.accuracy)}m > ${maxAccuracy}m threshold`,
    }
  }
  if (
    state?.lastTimeMs &&
    Number.isFinite(state.lastTimeMs) &&
    now - state.lastTimeMs < minInterval
  ) {
    return { accept: false, reason: 'minInterval' }
  }
  if (
    state?.lastPoint &&
    minDistanceM > 0 &&
    haversineMeters(state.lastPoint, [position.lon, position.lat]) < minDistanceM
  ) {
    return { accept: false, reason: 'minDistanceM' }
  }
  return { accept: true }
}

/**
 * Encapsulate GPS track recording primitives.
 *
 * Manages: trackStatus, trackInfo, liveTrack, trackDraftRef, watchRef,
 * syncDraftIntoUi, setStoredTrackDraft, clearTrackWatch, pauseTrackDraft,
 * handleTrackPoint.
 *
 * Extracted from FieldOpsTab.jsx lines 894-1051.
 *
 * @param {Object} options
 * @param {Function} options.setSurveyState  — functional updater for survey state
 * @param {Function} options.setCurrentPosition — update current GPS position
 * @param {Function} options.setError — set error message
 */
export default function useTrackRecording({ setSurveyState, setCurrentPosition, setError }) {
  const [liveTrack, setLiveTrack] = useState(null)
  const [trackStatus, setTrackStatus] = useState('idle')
  const [trackInfo, setTrackInfo] = useState({ points: 0, distance_m: 0 })
  const [transectSession, setTransectSession] = useState({
    route_id: '',
    observer: '',
    weather: '',
    notes: '',
    started_at: '',
    ended_at: '',
  })

  const watchRef = useRef(null)
  const trackDraftRef = useRef(createEmptyTrackDraft())

  function syncDraftIntoUi(draft) {
    trackDraftRef.current = draft || createEmptyTrackDraft()
    setLiveTrack(
      draft?.points?.length > 1
        ? {
          geometry: { type: 'LineString', coordinates: [...draft.points] },
          started_at: draft.started_at,
        }
        : null,
    )
    setTrackInfo({
      points: draft?.points?.length || 0,
      distance_m: lineDistanceMeters(draft?.points || []),
    })
    setTrackStatus(
      draft?.tracking_status === 'recording'
        ? 'recording'
        : draft?.tracking_status === 'paused'
          ? 'paused'
          : 'idle',
    )
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

  async function clearTrackWatch() {
    const currentWatch = watchRef.current
    watchRef.current = null
    if (!currentWatch) return

    if (currentWatch.kind === 'native') {
      await stopNativePositionWatch(currentWatch.id)
      return
    }

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
    if (pausedDraft) {
      setStoredTrackDraft(pausedDraft)
    }
    if (message) {
      setError(message)
    }
  }

  function handleTrackPoint(position, options = {}) {
    const existingPoints = trackDraftRef.current?.points || []
    const existingTimes = trackDraftRef.current?.point_times || []
    const lastPoint = existingPoints[existingPoints.length - 1] || null
    const lastTimeMs = existingTimes.length
      ? new Date(existingTimes[existingTimes.length - 1]).getTime()
      : 0
    const now = Date.now()
    const decision = decideTrackPointAcceptance(
      position,
      { lastPoint, lastTimeMs, now },
      options,
    )
    if (!decision.accept) {
      if (decision.reason && decision.reason.startsWith('GPS accuracy')) {
        setTrackInfo((prev) => ({ ...prev, lastSkipReason: decision.reason }))
      }
      return
    }

    const timestamp = new Date(position.timestamp || now).toISOString()
    const nextDraft = normalizeTrackDraft({
      ...(trackDraftRef.current || createEmptyTrackDraft()),
      points: [...existingPoints, [position.lon, position.lat]],
      point_times: [...existingTimes, timestamp],
      tracking_status: 'recording',
    })

    if (!nextDraft) return

    setCurrentPosition({
      lat: position.lat,
      lon: position.lon,
      accuracy: position.accuracy,
      timestamp: position.timestamp || now,
    })
    setStoredTrackDraft(nextDraft)
  }

  return {
    liveTrack,
    trackStatus,
    trackInfo,
    transectSession,
    setTransectSession,
    trackDraftRef,
    watchRef,
    syncDraftIntoUi,
    setStoredTrackDraft,
    clearTrackWatch,
    pauseTrackDraft,
    handleTrackPoint,
  }
}
