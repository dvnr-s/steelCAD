/**
 * Display formatting helpers.
 */

// Round off floating-point drift from ratio-based layout math (relayout can yield
// 4.7499999999999999 for a clean 4.75) and drop trailing zeros. Region dimensions
// are grid-aligned (0.25ft), so 2-decimal rounding is exact for real values.
export const fmtFt = (n) => String(Math.round(Number(n) * 100) / 100)

// Region dimension label in height × width order (fabrication convention).
export const dimLabel = (region) => `${fmtFt(region.height)}×${fmtFt(region.width)}`
