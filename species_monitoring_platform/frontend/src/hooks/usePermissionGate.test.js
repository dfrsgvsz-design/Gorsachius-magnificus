import { describe, expect, it, vi } from 'vitest'
import { reducePermissionGateState } from './usePermissionGate'
import { getPermissionCopy, listPermissionIds, PERMISSIONS } from '../lib/permissionCopy'

// State machine -----------------------------------------------------------

describe('reducePermissionGateState', () => {
  it('starts pristine and moves to prompting on a request event', () => {
    expect(reducePermissionGateState('pristine', 'request')).toBe('prompting')
  })

  it('keeps granted on request (no need to re-prompt)', () => {
    expect(reducePermissionGateState('granted', 'request')).toBe('granted')
  })

  it('moves prompting → pending on accept (waiting for OS dialog)', () => {
    expect(reducePermissionGateState('prompting', 'accept')).toBe('pending')
  })

  it('moves prompting → denied on skip', () => {
    expect(reducePermissionGateState('prompting', 'skip')).toBe('denied')
  })

  it('ignores accept/skip from non-prompting states', () => {
    expect(reducePermissionGateState('granted', 'accept')).toBe('granted')
    expect(reducePermissionGateState('blocked', 'skip')).toBe('blocked')
  })

  it('lets the native side promote to granted / denied / blocked', () => {
    expect(reducePermissionGateState('pending', 'native_granted')).toBe('granted')
    expect(reducePermissionGateState('pending', 'native_denied')).toBe('denied')
    expect(reducePermissionGateState('pending', 'native_blocked')).toBe('blocked')
  })

  it('reset always returns to pristine', () => {
    for (const state of ['pristine', 'prompting', 'pending', 'granted', 'denied', 'blocked']) {
      expect(reducePermissionGateState(state, 'reset')).toBe('pristine')
    }
  })

  it('drops unknown events without mutating state', () => {
    expect(reducePermissionGateState('granted', 'noop')).toBe('granted')
    expect(reducePermissionGateState('denied', 'unknown')).toBe('denied')
  })
})

// Copy registry -----------------------------------------------------------

describe('permissionCopy', () => {
  it('exposes all four sensitive runtime permissions', () => {
    expect(listPermissionIds().sort()).toEqual(
      ['backgroundLocation', 'camera', 'location', 'microphone'].sort(),
    )
  })

  it('serves localized Chinese copy by default', () => {
    const copy = getPermissionCopy('location', 'zh')
    expect(copy.rationale.title).toBe('需要使用你的位置')
    expect(copy.denied.headline).toBe('已拒绝定位')
    expect(copy.recoverHint).toContain('设置')
  })

  it('serves English copy when locale is en', () => {
    const copy = getPermissionCopy('camera', 'en')
    expect(copy.rationale.title).toBe('Camera is required')
    expect(copy.denied.headline).toBe('Camera denied')
  })

  it('falls back to English when locale is unknown', () => {
    const copy = getPermissionCopy('microphone', 'jp')
    expect(copy.rationale.title).toBe('Microphone is required')
  })

  it('returns null for unknown permission ids', () => {
    expect(getPermissionCopy('bluetooth', 'zh')).toBeNull()
  })

  it('every permission entry exposes the four anchored rationale fields', () => {
    for (const id of listPermissionIds()) {
      const entry = PERMISSIONS[id]
      for (const lang of ['zh', 'en']) {
        expect(entry.rationale[lang]).toMatchObject({
          title: expect.any(String),
          scene: expect.any(String),
          when: expect.any(String),
          benefit: expect.any(String),
          action: expect.any(String),
          skip: expect.any(String),
        })
        expect(entry.denied[lang]).toMatchObject({
          headline: expect.any(String),
          body: expect.any(String),
          degradedMode: expect.any(String),
        })
      }
    }
  })
})

// Smoke test: integration shape with native callbacks ----------------------

describe('usePermissionGate native shape', () => {
  it('chains native_granted via the request callback (state-machine smoke)', async () => {
    const sequence = ['pristine']
    const check = vi.fn(async () => 'prompt')
    const request = vi.fn(async () => 'granted')

    let state = 'pristine'
    state = reducePermissionGateState(state, 'request')
    sequence.push(state)
    await check()
    state = reducePermissionGateState(state, 'accept')
    sequence.push(state)
    const result = await request()
    state = reducePermissionGateState(state, `native_${result}`)
    sequence.push(state)

    expect(sequence).toEqual(['pristine', 'prompting', 'pending', 'granted'])
    expect(check).toHaveBeenCalledTimes(1)
    expect(request).toHaveBeenCalledTimes(1)
  })
})
