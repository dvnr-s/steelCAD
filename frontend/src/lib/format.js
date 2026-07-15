/**
 * Display formatting helpers.
 */

// Round off floating-point drift from ratio-based layout math (relayout can yield
// 4.7499999999999999 for a clean 4.75) and drop trailing zeros. Region dimensions
// are grid-aligned (0.25ft), so 2-decimal rounding is exact for real values.
export const fmtFt = (n) => String(Math.round(Number(n) * 100) / 100)

// Feet-and-inches display (fabrication convention): 5.5 → 5'6", 5 → 5',
// 0.75 → 9". Geometry is grid-aligned to 0.25 ft, so inches are always whole;
// rounding to the nearest inch also absorbs float drift.
export const fmtFtIn = (n) => {
  const totalIn = Math.round(Number(n) * 12)
  const ft = Math.trunc(totalIn / 12)
  const inch = totalIn % 12
  if (ft === 0 && inch !== 0) return `${inch}"`
  return inch === 0 ? `${ft}'` : `${ft}'${inch}"`
}

/**
 * Parse a dimension input into decimal feet. Accepts decimal feet (`5.5`),
 * feet-and-inches (`5'6"`, `5' 6`, `5ft 6in`, `5'`), inches only (`66"`, `9in`),
 * and smart quotes. Returns a number, or null when the input isn't parseable.
 */
export const parseFt = (raw) => {
  if (raw == null) return null
  const s = String(raw).trim().replace(/[’′]/g, "'").replace(/[”″]/g, '"')
  if (!s) return null
  if (/^\d+(\.\d+)?$/.test(s)) return parseFloat(s)
  const IN = '(?:"|in(?:ch(?:es)?)?)'
  let m = s.match(new RegExp(`^(\\d+(?:\\.\\d+)?)\\s*${IN}$`, 'i'))
  if (m) return parseFloat(m[1]) / 12
  m = s.match(new RegExp(`^(\\d+(?:\\.\\d+)?)\\s*(?:'|ft|feet)(?:\\s*(\\d+(?:\\.\\d+)?)\\s*${IN}?)?$`, 'i'))
  if (m) return parseFloat(m[1]) + (m[2] ? parseFloat(m[2]) / 12 : 0)
  return null
}

// Region dimension label in height × width order (fabrication convention).
export const dimLabel = (region) => `${fmtFtIn(region.height)}×${fmtFtIn(region.width)}`
