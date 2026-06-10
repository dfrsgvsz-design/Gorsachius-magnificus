import { useRef, useState } from 'react'
import {
  createEmptyTrackDraft,
  normalizeTrackDraft,
} from '../lib/fieldOpsDrafts'
import {
  lineDistanceMeters,
} from '../lib/surveyOffline'
import {
  stopNativePositionWatch,
} from '../lib/mobileNative'

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

  function handleTrackPoint(position, { maxAccuracy = 30, minInterval = 3000 } = {}) {
    if (position.accuracy != null && position.accuracy > maxAccuracy) {
      setTrackInfo((prev) => ({
        ...prev,
        lastSkipReason: `GPS accuracy ${Math.round(position.accuracy)}m > ${maxAccuracy}m threshold`,
      }))
      return
    }

    const now = Date.now()
    const lastTime = trackDraftRef.current?.point_times?.length
      ? new Date(trackDraftRef.current.point_times[trackDraftRef.current.point_times.length - 1]).getTime()
      : 0
    if (lastTime && (now - lastTime) < minInterval) {
      return
    }

    const timestamp = new Date(position.timestamp || now).toISOString()
    const nextDraft = normalizeTrackDraft({
      ...(trackDraftRef.current || createEmptyTrackDraft()),
      points: [...(trackDraftRef.current?.points || []), [position.lon, position.lat]],
      point_times: [...(trackDraftRef.current?.point_times || []), timestamp],
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
