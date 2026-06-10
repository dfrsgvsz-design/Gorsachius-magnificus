import { describe, expect, it, vi } from 'vitest'
import {
  buildAudioFile,
  checkAudioCaptureSupport,
  pickPreferredAudioMimeType,
} from './useAudioCapture'

// pickPreferredAudioMimeType ----------------------------------------------

describe('pickPreferredAudioMimeType', () => {
  it('returns an empty string when the recorder shim is missing', () => {
    expect(pickPreferredAudioMimeType(undefined)).toBe('')
    expect(pickPreferredAudioMimeType(null)).toBe('')
    expect(pickPreferredAudioMimeType({})).toBe('')
  })

  it('prefers webm/opus when the recorder advertises support', () => {
    const recorder = { isTypeSupported: vi.fn(() => true) }
    expect(pickPreferredAudioMimeType(recorder)).toBe('audio/webm;codecs=opus')
    expect(recorder.isTypeSupported).toHaveBeenCalledWith('audio/webm;codecs=opus')
  })

  it('falls back to ogg/opus when webm/opus is not supported', () => {
    const recorder = {
      isTypeSupported: vi.fn((type) => type === 'audio/ogg;codecs=opus'),
    }
    expect(pickPreferredAudioMimeType(recorder)).toBe('audio/ogg;codecs=opus')
    expect(recorder.isTypeSupported).toHaveBeenCalledWith('audio/webm;codecs=opus')
    expect(recorder.isTypeSupported).toHaveBeenCalledWith('audio/ogg;codecs=opus')
  })

  it('returns empty string to let the browser pick when nothing matches', () => {
    const recorder = { isTypeSupported: vi.fn(() => false) }
    expect(pickPreferredAudioMimeType(recorder)).toBe('')
  })
})

// buildAudioFile -----------------------------------------------------------

describe('buildAudioFile', () => {
  it('returns null when no chunks were captured', () => {
    expect(buildAudioFile([], 'audio/webm', 1000)).toBeNull()
    expect(buildAudioFile(undefined, 'audio/webm', 1000)).toBeNull()
    expect(buildAudioFile([null, undefined], 'audio/webm', 1000)).toBeNull()
  })

  it('produces a .webm File when the mime type is webm', () => {
    const chunk = new Blob([new Uint8Array([1, 2, 3])], { type: 'audio/webm' })
    const file = buildAudioFile([chunk], 'audio/webm;codecs=opus', 1234567890)
    expect(file).toBeInstanceOf(File)
    expect(file.name).toBe('field-audio-1234567890.webm')
    expect(file.type).toBe('audio/webm;codecs=opus')
    expect(file.size).toBeGreaterThan(0)
  })

  it('produces a .ogg File when the mime type is ogg', () => {
    const chunk = new Blob([new Uint8Array([4, 5, 6])], { type: 'audio/ogg' })
    const file = buildAudioFile([chunk], 'audio/ogg;codecs=opus', 1234567890)
    expect(file.name).toBe('field-audio-1234567890.ogg')
    expect(file.type).toBe('audio/ogg;codecs=opus')
  })

  it('defaults to webm when no mime is provided', () => {
    const chunk = new Blob([new Uint8Array([7, 8])])
    const file = buildAudioFile([chunk], '', 42)
    expect(file.name).toBe('field-audio-42.webm')
    expect(file.type).toBe('audio/webm')
  })

  it('uses Date.now() when timestampMs is omitted', () => {
    const chunk = new Blob([new Uint8Array([9])])
    const before = Date.now()
    const file = buildAudioFile([chunk], 'audio/webm')
    const after = Date.now()
    const match = file.name.match(/^field-audio-(\d+)\.webm$/)
    expect(match).not.toBeNull()
    const ts = Number(match[1])
    expect(ts).toBeGreaterThanOrEqual(before)
    expect(ts).toBeLessThanOrEqual(after)
  })
})

// checkAudioCaptureSupport ------------------------------------------------

describe('checkAudioCaptureSupport', () => {
  const fullEnv = () => ({
    window: {},
    navigator: { mediaDevices: { getUserMedia: () => Promise.resolve({}) } },
    MediaRecorder: function MockRecorder() {},
  })

  it('reports supported when all globals are present', () => {
    expect(checkAudioCaptureSupport(fullEnv())).toEqual({ supported: true })
  })

  it('reports no_window when window is missing', () => {
    const env = fullEnv()
    env.window = null
    expect(checkAudioCaptureSupport(env)).toEqual({
      supported: false,
      reason: 'no_window',
    })
  })

  it('reports no_get_user_media when getUserMedia is missing', () => {
    const env = fullEnv()
    env.navigator = {}
    expect(checkAudioCaptureSupport(env)).toEqual({
      supported: false,
      reason: 'no_get_user_media',
    })
  })

  it('reports no_get_user_media when navigator itself is missing', () => {
    const env = fullEnv()
    env.navigator = null
    expect(checkAudioCaptureSupport(env)).toEqual({
      supported: false,
      reason: 'no_get_user_media',
    })
  })

  it('reports no_media_recorder when the MediaRecorder global is missing', () => {
    const env = fullEnv()
    env.MediaRecorder = null
    expect(checkAudioCaptureSupport(env)).toEqual({
      supported: false,
      reason: 'no_media_recorder',
    })
  })
})
