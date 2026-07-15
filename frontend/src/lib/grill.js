/**
 * SS grill bar math — the single source of truth for how many bars a grilled
 * region carries and where they sit (spec §6.2 / §6.2A). Mirrored by the
 * backend (services/grill.py) so the bars drawn on canvas, thumbnails and the
 * PDF are exactly the bars billed.
 */

// Round-half-up, matching the backend's int(x + 0.5) so both sides always
// agree on the bar count (Math.round rounds halves toward +∞ for positives).
const roundHalfUp = (x) => Math.floor(x + 0.5)

/** Auto bar count from the spec formula: max(0, round((2 × h) − 2)). */
export const ssGrillAutoBars = (heightFt) => Math.max(0, roundHalfUp(2 * heightFt - 2))

/** Effective (billed = drawn) count: auto + manual delta (§6.2A). */
export const ssGrillBarCount = (heightFt, barAdjust = 0) =>
  Math.max(0, ssGrillAutoBars(heightFt) + (barAdjust || 0))

/** Most bars a region can hold at the 2" pitch limit (V-20). */
export const ssGrillMaxBars = (heightFt) => Math.floor(heightFt * 6)

/** The barAdjust delta stored on a grill overlay node (0 when unset). */
export const grillBarAdjust = (overlay) => overlay?.config?.barAdjust || 0

/**
 * Y offsets (feet from the region top) where bars are drawn (spec §6.2
 * rendering rule): the billed bars distributed evenly across the region's
 * full height — gap = h / (bars + 1) — so the pattern always fills the region
 * with equal spacing, whatever the count.
 */
export function ssGrillBarOffsets(heightFt, barAdjust = 0) {
  const bars = ssGrillBarCount(heightFt, barAdjust)
  if (bars <= 0) return []
  const gap = heightFt / (bars + 1)
  return Array.from({ length: bars }, (_, i) => gap * (i + 1))
}
