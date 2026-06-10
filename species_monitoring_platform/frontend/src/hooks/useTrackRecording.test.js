import { describe, expect, it } from 'vitest'
import { decideTrackPointAcceptance } from './useTrackRecording'

// 5m/3s denoising contract for the field workflow.
// Helpers --------------------------------------------------------------

const HAINAN_LAT = 19.5
const HAINAN_LON = 109.5
const METERS_PER_DEG_LAT = 110540

function lonOffsetMeters(meters, lat = HAINAN_LAT) {
  const metersPerLon = 111320 * Math.cos((lat * Math.PI) / 180)
  return meters / metersPerLon
}

function pos({ dLatMeters = 0, dLonMeters = 0, accuracy = 5 }) {
  return {
    lat: HAINAN_LAT + dLatMeters / METERS_PER_DEG_LAT,
    lon: HAINAN_LON + lonOffsetMeters(dLonMeters),
    accuracy,
  }
}

const EMPTY_STATE = { lastPoint: null, lastTimeMs: 0, now: 1000 }

// Accuracy gate -------------------------------------------------------

describe('decideTrackPointAcceptance accuracy gate', () => {
  it('accepts the first fix when accuracy is within threshold', () => {
    expect(decideTrackPointAcceptance(pos({ accuracy: 10 }), EMPTY_STATE)).toEqual({
      accept: true,
    })
  })

  it('rejects fixes whose reported accuracy is worse than maxAccuracy', () => {
    const decision = decideTrackPointAcceptance(pos({ accuracy: 80 }), EMPTY_STATE)
    expect(decision.accept).toBe(false)
    expect(decision.reason).toMatch(/GPS accuracy 80m/)
  })

  it('respects the configurable maxAccuracy override', () => {
    expect(
      decideTrackPointAcceptance(pos({ accuracy: 12 }), EMPTY_STATE, {
        maxAccuracy: 10,
      }).accept,
    ).toBe(false)
    expect(
      decideTrackPointAcceptance(pos({ accuracy: 12 }), EMPTY_STATE, {
        maxAccuracy: 50,
      }).accept,
    ).toBe(true)
  })

  it('tolerates fixes that omit an accuracy field', () => {
    const decision = decideTrackPointAcceptance(
      { lat: HAINAN_LAT, lon: HAINAN_LON },
      EMPTY_STATE,
    )
    expect(decision.accept).toBe(true)
  })
})

// Time gate -----------------------------------------------------------

describe('decideTrackPointAcceptance time gate', () => {
  it('drops fixes that arrive sooner than the default minInterval of 3 s', () => {
    const state = {
      lastPoint: [HAINAN_LON, HAINAN_LAT],
      lastTimeMs: 10_000,
      now: 11_500,
    }
    expect(
      decideTrackPointAcceptance(pos({ dLatMeters: 50 }), state).accept,
    ).toBe(false)
  })

  it('accepts fixes once minInterval has elapsed (>= 3 s)', () => {
    const state = {
      lastPoint: [HAINAN_LON, HAINAN_LAT],
      lastTimeMs: 10_000,
      now: 13_500,
    }
    expect(
      decideTrackPointAcceptance(pos({ dLatMeters: 50 }), state).accept,
    ).toBe(true)
  })
})

// Distance gate -------------------------------------------------------

describe('decideTrackPointAcceptance distance gate', () => {
  const FAR_FUTURE = { lastPoint: [HAINAN_LON, HAINAN_LAT], lastTimeMs: 10_000, now: 99_999 }

  it('drops fixes closer than minDistanceM even after the time gate clears', () => {
    expect(
      decideTrackPointAcceptance(pos({ dLatMeters: 1 }), FAR_FUTURE).accept,
    ).toBe(false)
    expect(
      decideTrackPointAcceptance(pos({ dLatMeters: 1 }), FAR_FUTURE).reason,
    ).toBe('minDistanceM')
  })

  it('accepts fixes farther than minDistanceM', () => {
    expect(
      decideTrackPointAcceptance(pos({ dLatMeters: 10 }), FAR_FUTURE).accept,
    ).toBe(true)
  })

  it('respects minDistanceM=0 to bypass the distance gate', () => {
    expect(
      decideTrackPointAcceptance(pos({ dLatMeters: 0.2 }), FAR_FUTURE, {
        minDistanceM: 0,
      }).accept,
    ).toBe(true)
  })
})

// Composite behavior --------------------------------------------------

describe('decideTrackPointAcceptance composite', () => {
  it('always accepts the very first fix regardless of distance/time', () => {
    expect(
      decideTrackPointAcceptance(pos({ dLatMeters: 0 }), EMPTY_STATE).accept,
    ).toBe(true)
  })

  it('accepts a point that clears all three gates', () => {
    const state = {
      lastPoint: [HAINAN_LON, HAINAN_LAT],
      lastTimeMs: 10_000,
      now: 14_000,
    }
    const decision = decideTrackPointAcceptance(
      pos({ dLatMeters: 10, accuracy: 8 }),
      state,
    )
    expect(decision).toEqual({ accept: true })
  })
})
