import { describe, it, expect } from 'vitest'
import { fmtFt, fmtFtIn, parseFt, dimLabel } from './format'

describe('fmtFtIn', () => {
  it('formats whole feet without an inches part', () => {
    expect(fmtFtIn(5)).toBe("5'")
    expect(fmtFtIn(0)).toBe("0'")
  })

  it('formats feet + inches', () => {
    expect(fmtFtIn(5.5)).toBe('5\'6"')
    expect(fmtFtIn(2.25)).toBe('2\'3"')
    expect(fmtFtIn(3.75)).toBe('3\'9"')
  })

  it('formats sub-foot values as inches only', () => {
    expect(fmtFtIn(0.75)).toBe('9"')
    expect(fmtFtIn(0.5)).toBe('6"')
  })

  it('absorbs float drift from ratio layout math', () => {
    expect(fmtFtIn(4.75 - 1e-13)).toBe('4\'9"')
    expect(fmtFtIn(2.499999999)).toBe('2\'6"')
  })
})

describe('parseFt', () => {
  it('parses decimal feet', () => {
    expect(parseFt('5')).toBe(5)
    expect(parseFt('5.5')).toBe(5.5)
    expect(parseFt(' 3.25 ')).toBe(3.25)
  })

  it('parses feet-and-inches in common spellings', () => {
    expect(parseFt('5\'6"')).toBe(5.5)
    expect(parseFt("5'6")).toBe(5.5)
    expect(parseFt("5' 6\"")).toBe(5.5)
    expect(parseFt('5ft 6in')).toBe(5.5)
    expect(parseFt('5 ft 6')).toBe(5.5)
    expect(parseFt("5'")).toBe(5)
    expect(parseFt('5ft')).toBe(5)
  })

  it('parses inches-only values', () => {
    expect(parseFt('66"')).toBe(5.5)
    expect(parseFt('9in')).toBe(0.75)
    expect(parseFt('6 inches')).toBe(0.5)
  })

  it('handles smart quotes from mobile keyboards', () => {
    expect(parseFt('5’6”')).toBe(5.5)
  })

  it('rejects garbage', () => {
    expect(parseFt('')).toBeNull()
    expect(parseFt('abc')).toBeNull()
    expect(parseFt('5x6')).toBeNull()
    expect(parseFt(null)).toBeNull()
    expect(parseFt('-3')).toBeNull()
  })
})

describe('fmtFt', () => {
  it('rounds drift and drops trailing zeros', () => {
    expect(fmtFt(4.75 - 1e-13)).toBe('4.75')
    expect(fmtFt(4)).toBe('4')
  })
})

describe('dimLabel', () => {
  it('renders height × width in ft-in', () => {
    expect(dimLabel({ height: 4, width: 2.5 })).toBe('4\'×2\'6"')
  })
})
