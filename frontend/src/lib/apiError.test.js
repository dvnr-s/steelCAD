import { describe, it, expect } from 'vitest'
import { apiError } from './apiError'

const err = (detail) => ({ response: { data: { detail } } })

describe('apiError', () => {
  it('passes through a string detail', () => {
    expect(apiError(err('Estimate is locked'), 'fallback')).toBe('Estimate is locked')
  })

  it('flattens a FastAPI 422 validation array into a string', () => {
    const detail = [{ loc: ['body', 'email'], msg: 'value is not a valid email address', type: 'value_error' }]
    expect(apiError(err(detail), 'fallback')).toBe('email: value is not a valid email address')
  })

  it('omits a bare "body" location', () => {
    expect(apiError(err([{ loc: ['body'], msg: 'Field required' }]), 'fallback')).toBe('Field required')
  })

  it('falls back for missing, empty or object details and network errors', () => {
    expect(apiError(err(undefined), 'fallback')).toBe('fallback')
    expect(apiError(err([]), 'fallback')).toBe('fallback')
    expect(apiError(err({ validation_errors: ['x'] }), 'fallback')).toBe('fallback')
    expect(apiError(new Error('Network Error'), 'fallback')).toBe('fallback')
  })
})
