/**
 * HomePage — metrics rendering and the 300ms-debounced global quote search.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../api/client', () => ({
  default: { get: vi.fn(), post: vi.fn() },
  dashboardApi: { metrics: vi.fn() },
  estimatesApi: { search: vi.fn() },
  authApi: { changePassword: vi.fn() },
}))

import { dashboardApi, estimatesApi } from '../api/client'
import HomePage from './HomePage'

const METRICS = {
  pipeline: [
    { status: 'draft', count: 3, total: 5000 },
    { status: 'accepted', count: 1, total: 12000 },
  ],
  monthly_revenue: [
    { month: '2026-06-01', total: 8000 },
    { month: '2026-07-01', total: 12000 },
  ],
  active_customers: 4,
  active_designs: 2,
  recent_estimates: [{
    id: 'e-1', number: 12, revision: 1, title: 'Recent Q', status: 'draft',
    customer_id: 'c-1', customer_name: 'ACME Corp', frame_count: 1,
    grand_total: 5000, is_expired: false,
    created_at: '2026-07-01T00:00:00Z', updated_at: '2026-07-01T00:00:00Z',
  }],
}

const renderPage = () => render(<MemoryRouter><HomePage /></MemoryRouter>)

beforeEach(() => {
  vi.clearAllMocks()
  dashboardApi.metrics.mockResolvedValue({ data: METRICS })
  estimatesApi.search.mockResolvedValue({ data: [] })
})

afterEach(() => {
  vi.useRealTimers()
})

describe('HomePage', () => {
  it('renders pipeline cards, revenue bars, and recent estimates', async () => {
    renderPage()
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument()
    // Pipeline counts + totals
    expect(screen.getByText('3')).toBeInTheDocument()
    // appears in both the accepted pipeline card and the July revenue bar
    expect(screen.getAllByText('₹12,000').length).toBeGreaterThanOrEqual(2)
    // Entity counts line
    expect(screen.getByText(/4 customers · 2 designs/)).toBeInTheDocument()
    // Recent estimate row
    expect(screen.getByText('EST-0012')).toBeInTheDocument()
    expect(screen.getByText('ACME Corp')).toBeInTheDocument()
    // Revenue section header
    expect(screen.getByText(/Accepted revenue/)).toBeInTheDocument()
  })

  it('debounces the global search by 300ms', async () => {
    renderPage()
    const input = await screen.findByPlaceholderText(/Search quotes/)

    vi.useFakeTimers()
    fireEvent.change(input, { target: { value: 'acme' } })
    expect(estimatesApi.search).not.toHaveBeenCalled()

    await act(async () => { vi.advanceTimersByTime(299) })
    expect(estimatesApi.search).not.toHaveBeenCalled()

    await act(async () => { vi.advanceTimersByTime(1) })
    expect(estimatesApi.search).toHaveBeenCalledTimes(1)
    expect(estimatesApi.search).toHaveBeenCalledWith({ q: 'acme', limit: 20 })
  })

  it('typing again within the window restarts the debounce', async () => {
    renderPage()
    const input = await screen.findByPlaceholderText(/Search quotes/)

    vi.useFakeTimers()
    fireEvent.change(input, { target: { value: 'ac' } })
    await act(async () => { vi.advanceTimersByTime(200) })
    fireEvent.change(input, { target: { value: 'acme' } })
    await act(async () => { vi.advanceTimersByTime(200) })
    expect(estimatesApi.search).not.toHaveBeenCalled()

    await act(async () => { vi.advanceTimersByTime(100) })
    expect(estimatesApi.search).toHaveBeenCalledTimes(1)
    expect(estimatesApi.search).toHaveBeenCalledWith({ q: 'acme', limit: 20 })
  })
})
