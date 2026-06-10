import { describe, expect, it, vi } from 'vitest'
import { capturePhotoWithState } from './useCameraCapture'

function makeCallbacks() {
  const calls = { serializing: [], errors: [], attachments: [] }
  return {
    calls,
    onSerializing: vi.fn((value) => calls.serializing.push(value)),
    onError: vi.fn((value) => calls.errors.push(value)),
    onAttachment: vi.fn((value) => calls.attachments.push(value)),
  }
}

describe('capturePhotoWithState', () => {
  it('fires onSerializing(true) then onError(null) before invoking captureFn', async () => {
    const order = []
    const captureFn = vi.fn(async () => {
      order.push('captureFn')
      return null
    })
    const cb = {
      onSerializing: (value) => order.push(`serializing:${value}`),
      onError: (value) => order.push(`error:${String(value)}`),
      onAttachment: () => order.push('attachment'),
    }
    await capturePhotoWithState({ captureFn, source: 'CAMERA', callbacks: cb })
    expect(order[0]).toBe('serializing:true')
    expect(order[1]).toBe('error:null')
    expect(order[2]).toBe('captureFn')
    expect(captureFn).toHaveBeenCalledWith('CAMERA')
  })

  it('returns ok=true with the captured attachment and fires onAttachment', async () => {
    const attachment = { attachment_id: 'att_123', filename: 'shot.jpg' }
    const captureFn = vi.fn(async () => attachment)
    const cb = makeCallbacks()
    const result = await capturePhotoWithState({
      captureFn,
      source: 'CAMERA',
      callbacks: cb,
    })
    expect(result).toEqual({ ok: true, attachment })
    expect(cb.onAttachment).toHaveBeenCalledTimes(1)
    expect(cb.onAttachment).toHaveBeenCalledWith(attachment)
    expect(cb.calls.serializing).toEqual([true, false])
  })

  it('returns ok=true with null attachment when the user dismissed the camera', async () => {
    const captureFn = vi.fn(async () => null)
    const cb = makeCallbacks()
    const result = await capturePhotoWithState({
      captureFn,
      source: 'CAMERA',
      callbacks: cb,
    })
    expect(result).toEqual({ ok: true, attachment: null })
    expect(cb.onAttachment).not.toHaveBeenCalled()
    expect(cb.calls.serializing).toEqual([true, false])
  })

  it('propagates errors via onError and returns ok=false', async () => {
    const captureFn = vi.fn(async () => {
      throw new Error('Permission denied')
    })
    const cb = makeCallbacks()
    const result = await capturePhotoWithState({
      captureFn,
      source: 'CAMERA',
      callbacks: cb,
    })
    expect(result.ok).toBe(false)
    expect(result.error).toContain('Permission denied')
    expect(cb.onError).toHaveBeenLastCalledWith(expect.stringContaining('Permission denied'))
    expect(cb.calls.serializing).toEqual([true, false])
  })

  it('falls back to fallbackMessage when the error has no message', async () => {
    const captureFn = vi.fn(async () => {
      throw {}
    })
    const cb = makeCallbacks()
    const result = await capturePhotoWithState({
      captureFn,
      source: 'CAMERA',
      callbacks: cb,
      fallbackMessage: 'Custom fallback message',
    })
    expect(result.ok).toBe(false)
    expect(result.error).toBe('Custom fallback message')
  })

  it('always calls onSerializing(false) in finally, even on synchronous throws', async () => {
    const captureFn = vi.fn(() => {
      throw new Error('sync failure')
    })
    const cb = makeCallbacks()
    await capturePhotoWithState({ captureFn, source: 'CAMERA', callbacks: cb })
    expect(cb.calls.serializing).toEqual([true, false])
  })

  it('tolerates missing callbacks (they are all optional)', async () => {
    const captureFn = vi.fn(async () => ({ attachment_id: 'x' }))
    await expect(
      capturePhotoWithState({ captureFn, source: 'CAMERA' }),
    ).resolves.toMatchObject({ ok: true })
    await expect(
      capturePhotoWithState({
        captureFn: () => { throw new Error('boom') },
        source: 'CAMERA',
      }),
    ).resolves.toMatchObject({ ok: false })
  })
})
