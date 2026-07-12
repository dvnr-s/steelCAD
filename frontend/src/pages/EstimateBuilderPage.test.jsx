/**
 * EstimateBuilderPage rendering — totals rows (dynamic GST label), locked
 * banner, expired badge, revision heading. API fully mocked.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

vi.mock('../api/client', () => ({
  default: { get: vi.fn(), post: vi.fn() },
  estimatesApi: { get: vi.fn() },
  designsApi: { list: vi.fn().mockResolvedValue({ data: [] }) },
  authApi: { changePassword: vi.fn() },
}))

import { estimatesApi } from '../api/client'
import EstimateBuilderPage from './EstimateBuilderPage'

const FIXTURE = {
  id: 'e-1',
  number: 7,
  revision: 2,
  parent_id: 'e-0',
  title: 'Ground floor',
  notes: '',
  status: 'sent',
  quote_date: '2026-07-01',
  valid_until: '2026-06-01',
  terms: '',
  customer: { id: 'c-1', name: 'ACME Corp', company: 'ACME' },
  discount_type: null,
  discount_value: 0,
  advance_pct: 30,
  gst_pct: 12,
  is_expired: true,
  frames: [],
  subtotal: 1000,
  discount_amount: 0,
  taxable: 1000,
  gst: 120,
  grand_total: 1120,
  advance_amount: 336,
  created_at: '2026-07-01T00:00:00Z',
  updated_at: '2026-07-01T00:00:00Z',
}

const renderPage = () => render(
  <MemoryRouter initialEntries={['/estimates/e-1']}>
    <Routes>
      <Route path="/estimates/:id" element={<EstimateBuilderPage />} />
    </Routes>
  </MemoryRouter>,
)

beforeEach(() => {
  vi.clearAllMocks()
  estimatesApi.get.mockResolvedValue({ data: FIXTURE })
})

describe('EstimateBuilderPage', () => {
  it('renders the totals with the estimate-specific GST label', async () => {
    renderPage()
    expect(await screen.findByText('GST (12%)')).toBeInTheDocument()
    expect(screen.getByText('Taxable Amount')).toBeInTheDocument()
    expect(screen.getByText('Grand Total')).toBeInTheDocument()
    expect(screen.getByText(/Advance \(30%\)/)).toBeInTheDocument()
  })

  it('shows the locked banner with the revise guidance for a sent quote', async () => {
    renderPage()
    expect(await screen.findByText(/and locked/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Revise/ })).toBeInTheDocument()
  })

  it('shows the expired badge and revision heading', async () => {
    renderPage()
    expect(await screen.findByText('expired')).toBeInTheDocument()
    expect(screen.getByText('rev 2')).toBeInTheDocument()
    expect(screen.getByText(/EST-0007/)).toBeInTheDocument()
  })

  it('disables editing controls when locked', async () => {
    renderPage()
    const title = await screen.findByPlaceholderText('e.g. Ground floor windows')
    expect(title).toBeDisabled()
  })
})
