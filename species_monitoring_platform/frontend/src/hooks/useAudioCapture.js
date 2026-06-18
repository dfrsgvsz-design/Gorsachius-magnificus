import { useEffect, useRef, useState } from 'react'
import { serializeAttachment } from '../lib/surveyOffline'
import { getApiErrorMessage } from '../lib/api'
import { ImpactStyle, pulseFeedback } from '../lib/mobileNative'

// ---------------------------------------------------------------------------
// Pure helpers — exported for unit-testing without spinning up React or a DOM.
// ---------------------------------------------------------------------------

/**
 * Pick the preferred MIME type for a `MediaRecorder` instance. Prefers Opus
 * (smallest, browser-supported) and falls back to letting the browser choose.
 *
 * @param {object} mediaRecorderImpl  the `MediaRecorder` constructor or shim
 * @returns {string}  the negotiated mime type, or `''` to leave it unset
 */
export function pickPreferredAudioMimeType(mediaRecorderImpl) {
  if (!mediaRecorderImpl || typeof mediaRecorderImpl.isTypeSupported !== 'function') {
    return ''
  }
  if (mediaRecorderImpl.isTypeSupported('audio/webm;codecs=opus')) {
    return 'audio/webm;codecs=opus'
  }
  if (mediaRecorderImpl.isTypeSupported('audio/ogg;codecs=opus')) {
    return 'audio/ogg;codecs=opus'
  }
  return ''
}

/**
 * Wrap accumulated `MediaRecorder` chunks into a `File` whose extension and
 * MIME type match the negotiated container. Uses an injectable `timestampMs`
 * so test runs produce stable filenames.
 *
 * @param {Blob[]} chunks
 * @param {string} mimeType  preferred type (may be empty)
 * @param {number} [timestampMs]  defaults to `Date.now()`
 * @returns {File | null}  `null` when there are no audible chunks
 */
export function buildAudioFile(chunks, mimeType, timestampMs = Date.now()) {
  const safeChunks = Array.isArray(chunks) ? chunks.filter(Boolean) : []
  const effectiveType = mimeType || 'audio/webm'
  const blob = new Blob(safeChunks, { type: effectiveType })
  if (blob.size === 0) return null
  const extension = effectiveType.includes('ogg') ? 'ogg' : 'webm'
  return new File([blob], `field-audio-${timestampMs}.${extension}`, {
    type: effectiveType,
  })
}

/**
 * Report whether the current environment can capture audio. Tests inject the
 * relevant globals via `env` to exercise every branch.
 *
 * @returns {{ supported: boolean, reason?: string }}
 */
export function checkAudioCaptureSupport(env = {}) {
  const w = env.window ?? (typeof window === 'undefined' ? null : window)
  const nav = env.navigator ?? (typeof navigator === 'undefined' ? null : navigator)
  const recorder = env.MediaRecorder
    ?? (typeof MediaRecorder === 'undefined' ? null : MediaRecorder)
  if (!w) return { supported: false, reason: 'no_window' }
  if (!nav?.mediaDevices?.getUserMedia) return { supported: false, reason: 'no_get_user_media' }
  if (!recorder) return { supported: false, reason: 'no_media_recorder' }
  return { supported: true }
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * Encapsulate browser `MediaRecorder` audio capture for field surveys.
 *
 * `onAttachment(attachment)` fires when a finished recording is serialized
 * into the surveyOffline attachment store.
 * `onEvidenceType(type)` is called to set `evidence_type` to `'audio'` both at
 * start and at successful completion.
 * `onError(messageOrNull)` is called on failures (and with `null` to clear).
 *
 * @returns {{
 *   audioCaptureStatus: 'idle' | 'recording',
 *   serializingAudio: boolean,
 *   startAudioCapture: () => Promise<void>,
 *   stopAudioCapture: () => Promise<void>,
 * }}
 */
export default function useAudioCapture({
  onAttachment,
  onEvidenceType,
  onError,
  // Optional gate check from `usePermissionGate(...).createGateCheck()`.
  // When provided, `startAudioCapture` awaits it before calling
  // `navigator.mediaDevices.getUserMedia` so the rationale modal can
  // render first. When omitted, the hook keeps its original behaviour
  // (the browser/Capacitor will surface its own permission prompt).
  gateCheck,
} = {}) {
  const [audioCaptureStatus, setAudioCaptureStatus] = useState('idle')
  const [serializingMedia, setSerializingMedia] = useState(false)
  const audioRecorderRef = useRef(null)
  const audioStreamRef = useRef(null)
  const audioChunksRef = useRef([])

  useEffect(() => () => {
    if (audioRecorderRef.current && audioRecorderRef.current.state !== 'inactive') {
      audioRecorderRef.current.stop()
    }
    if (audioStreamRef.current) {
      audioStreamRef.current.getTracks().forEach((track) => track.stop())
      audioStreamRef.current = null
    }
  }, [])

  async function startAudioCapture() {
    const support = checkAudioCaptureSupport()
    if (!support.supported) {
      onError?.('Audio recording is not supported in this browser or device.')
      return
    }
    if (audioCaptureStatus === 'recording') return
    if (typeof gateCheck === 'function') {
      const allowed = await gateCheck()
      if (!allowed) {
        onError?.('Microphone permission was not granted.')
        return
      }
    }
    setSerializingMedia(true)
    onError?.(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mimeType = pickPreferredAudioMimeType(MediaRecorder)
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
      audioChunksRef.current = []
      audioStreamRef.current = stream
      audioRecorderRef.current = recorder
      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) audioChunksRef.current.push(event.data)
      }
      recorder.onstop = async () => {
        try {
          const negotiated = recorder.mimeType || mimeType || 'audio/webm'
          const file = buildAudioFile(audioChunksRef.current, negotiated)
          if (file) {
            const attachment = await serializeAttachment(file)
            onAttachment?.(attachment)
            onEvidenceType?.('audio')
            await pulseFeedback(ImpactStyle.Light)
          }
        } catch (err) {
          onError?.(getApiErrorMessage(err, 'Unable to save the recorded audio evidence.'))
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
      onEvidenceType?.('audio')
      setAudioCaptureStatus('recording')
      await pulseFeedback(ImpactStyle.Light)
    } catch (err) {
      setSerializingMedia(false)
      setAudioCaptureStatus('idle')
      onError?.(getApiErrorMessage(err, 'Unable to start audio recording on this device.'))
    }
  }

  async function stopAudioCapture() {
    if (!audioRecorderRef.current || audioRecorderRef.current.state === 'inactive') return
    try {
      audioRecorderRef.current.stop()
    } catch (err) {
      setSerializingMedia(false)
      setAudioCaptureStatus('idle')
      onError?.(getApiErrorMessage(err, 'Unable to stop audio recording cleanly.'))
    }
  }

  return {
    audioCaptureStatus,
    serializingAudio: serializingMedia,
    startAudioCapture,
    stopAudioCapture,
  }
}
