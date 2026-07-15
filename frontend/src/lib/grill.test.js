/**
 * SS grill bar math (spec §6.2 / §6.2A) — mirror of backend
 * app/services/grill.py (pinned there by tests/test_grill.py). Drawn bars
 * always equal billed bars, spread evenly across the region.
 */
import { describe, it, expect } from 'vitest'
import {
  grillBarAdjust,
  ssGrillAutoBars,
  ssGrillBarCount,
  ssGrillBarOffsets,
  ssGrillMaxBars,
} from './grill'

describe('ssGrillAutoBars', () => {
  it('follows max(0, round(2h − 2)) with half-up rounding', () => {
    expect(ssGrillAutoBars(1.0)).toBe(0)    // too short to earn a bar
    expect(ssGrillAutoBars(0.5)).toBe(0)    // never negative
    expect(ssGrillAutoBars(1.25)).toBe(1)   // 0.5 → 1 (half-up)
    expect(ssGrillAutoBars(2.5)).toBe(3)
    expect(ssGrillAutoBars(2.95)).toBe(4)   // 3.9 → 4 — whole bars only
    expect(ssGrillAutoBars(2.25)).toBe(3)   // 2.5 → 3 (matches backend int(x+0.5))
    expect(ssGrillAutoBars(5.0)).toBe(8)    // spec §6.2 example 1
    expect(ssGrillAutoBars(7.5)).toBe(13)
  })
})

describe('ssGrillBarCount / ssGrillMaxBars', () => {
  it('applies the manual delta and floors at zero', () => {
    expect(ssGrillBarCount(5.0, 2)).toBe(10)
    expect(ssGrillBarCount(5.0, -3)).toBe(5)
    expect(ssGrillBarCount(5.0, -20)).toBe(0) // validation rejects before this
  })

  it('caps at one bar per 2 inches of height', () => {
    expect(ssGrillMaxBars(5.0)).toBe(30)
    expect(ssGrillMaxBars(2.5)).toBe(15)
  })
})

describe('grillBarAdjust', () => {
  it('reads the delta from the overlay config, defaulting to 0', () => {
    expect(grillBarAdjust({ config: { barAdjust: 2 } })).toBe(2)
    expect(grillBarAdjust({ config: {} })).toBe(0)
    expect(grillBarAdjust({})).toBe(0)
    expect(grillBarAdjust(undefined)).toBe(0)
  })
})

describe('ssGrillBarOffsets', () => {
  it('spreads the billed bars evenly across the region (gap = h/(bars+1))', () => {
    expect(ssGrillBarOffsets(2.5)).toEqual([0.625, 1.25, 1.875])
    const tall = ssGrillBarOffsets(7.5) // 13 bars
    expect(tall).toHaveLength(13)
    const gap = 7.5 / 14
    expect(tall[0]).toBeCloseTo(gap)          // same gap above the first bar…
    expect(tall[12]).toBeCloseTo(7.5 - gap)   // …and below the last
    for (let i = 1; i < tall.length; i++) expect(tall[i] - tall[i - 1]).toBeCloseTo(gap)
  })

  it('centers a single bar and draws nothing when nothing is billed', () => {
    expect(ssGrillBarOffsets(1.25)).toEqual([0.625])
    expect(ssGrillBarOffsets(1.0)).toEqual([])
  })

  it('respaces automatically for adjusted counts — no fixed margins', () => {
    const offsets = ssGrillBarOffsets(7.5, 2) // 13 auto + 2 = 15 bars
    expect(offsets).toHaveLength(15)
    const gap = 7.5 / 16
    expect(offsets[0]).toBeCloseTo(gap)
    expect(offsets[14]).toBeCloseTo(7.5 - gap)
  })
})
