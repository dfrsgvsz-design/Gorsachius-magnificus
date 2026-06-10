import { describe, expect, it } from 'vitest'

/**
 * Mirror of `isTileCacheFresh` from `public/service-worker.js`. We import the
 * SW source as text and eval the function so the SW stays the source of
 * truth — keeping a hand-typed copy in this test file would be a portable
 * way to silently let the two definitions drift apart.
 *
 * The SW file is plain JS with no imports, so this is safe and the runner
 * stays node-only.
 */
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)
const swSource = readFileSync(
  join(__dirname, '..', '..', 'public', 'service-worker.js'),
  'utf8',
)

// Extract the function declaration verbatim (regex stops at the next blank
// line to keep us from accidentally grabbing the helper block below it).
const fnMatch = swSource.match(/function isTileCacheFresh\([\s\S]*?\n\}/)
if (!fnMatch) {
  throw new Error('isTileCacheFresh not found in service-worker.js')
}

// eslint-disable-next-line no-new-func
const isTileCacheFresh = new Function(
  `${fnMatch[0]}; return isTileCacheFresh;`,
)()

const DAY = 24 * 60 * 60 * 1000
const THIRTY_DAYS = 30 * DAY

describe('isTileCacheFresh', () => {
  it('treats a missing timestamp (0) as stale', () => {
    expect(isTileCacheFresh(0, Date.now(), THIRTY_DAYS)).toBe(false)
  })

  it('treats a NaN timestamp as stale', () => {
    expect(isTileCacheFresh(NaN, Date.now(), THIRTY_DAYS)).toBe(false)
  })

  it('treats a negative timestamp as stale (defensive against clock skew)', () => {
    expect(isTileCacheFresh(-1, Date.now(), THIRTY_DAYS)).toBe(false)
  })

  it('returns true for a tile cached 1 second ago', () => {
    const now = 1_700_000_000_000
    expect(isTileCacheFresh(now - 1_000, now, THIRTY_DAYS)).toBe(true)
  })

  it('returns true for a tile cached 29 days ago', () => {
    const now = 1_700_000_000_000
    expect(isTileCacheFresh(now - 29 * DAY, now, THIRTY_DAYS)).toBe(true)
  })

  it('returns true at exactly the TTL boundary (inclusive)', () => {
    const now = 1_700_000_000_000
    expect(isTileCacheFresh(now - THIRTY_DAYS, now, THIRTY_DAYS)).toBe(true)
  })

  it('returns false at TTL + 1 ms', () => {
    const now = 1_700_000_000_000
    expect(isTileCacheFresh(now - THIRTY_DAYS - 1, now, THIRTY_DAYS)).toBe(false)
  })

  it('returns false when `now` is invalid', () => {
    const cachedAt = 1_700_000_000_000
    expect(isTileCacheFresh(cachedAt, Number.NaN, THIRTY_DAYS)).toBe(false)
    expect(isTileCacheFresh(cachedAt, Number.POSITIVE_INFINITY, THIRTY_DAYS)).toBe(false)
  })

  it('returns false when ttlMs is invalid', () => {
    const now = 1_700_000_000_000
    expect(isTileCacheFresh(now - DAY, now, 0)).toBe(false)
    expect(isTileCacheFresh(now - DAY, now, -1)).toBe(false)
    expect(isTileCacheFresh(now - DAY, now, Number.NaN)).toBe(false)
  })

  it('asserts the SW constant equals 30 days (catches silent drift)', () => {
    const constMatch = swSource.match(/const TILE_CACHE_DURATION = (\d[\d *]+);/)
    expect(constMatch).not.toBeNull()
    const expression = constMatch[1].replace(/\s+/g, '')
    // eslint-disable-next-line no-new-func
    const value = new Function(`return ${expression}`)()
    expect(value).toBe(THIRTY_DAYS)
  })
})
