import { useEffect, useRef, useState } from 'react'
import { serializeAttachment } from '../lib/surveyOffline'
import { getApiErrorMessage } from '../lib/api'
import { ImpactStyle, pulseFeedback } from '../lib/mobileNative'

/**
 * Encapsulate browser MediaRecorder audio capture logic.
 *
 * Returns { audioCaptureStatus, startAudioCapture, stopAudioCapture }.
 *
 * `onAttachment(attachment)` is called when a finished recording is serialized.
 * `onEvidenceType(type)` is called to set evidence_type to 'audio'.
 * `onError(message)` is called on failures.
 *
 * Extracted from FieldOpsTab lines 1024, 1031-1033, 1281-1289, 2293-2361.
 */
export default function useAudioCapture({ onAttachment, onEvidenceType, onError }) {
  const [audioCaptureStatus, setAudioCaptureStatus] = useState('idle')
  const [serializingMedia, setSerializingMedia] = useState(false)
  const audioRecorderRef = useRef(null)
  const audioStreamRef = useRef(null)
  const audioChunksRef = useRef([])

  // cleanup on unmount
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
    if (
      typeof window === 'undefined'
      || !navigator?.mediaDevices?.getUserMedia
      || typeof MediaRecorder === 'undefined'
    ) {
      onError?.('Audio recording is not supported in this browser or device.')
      return
    }
    if (audioCaptureStatus === 'recording') return
    setSerializingMedia(true)
    onError?.(null)
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
