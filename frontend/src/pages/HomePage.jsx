/**
 * Home — business dashboard: pipeline metrics, monthly accepted revenue,
 * recent estimates, and a global quote search.
 */
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FileText, Users, LayoutGrid, Search, Clock } from 'lucide-react'
import toast from 'react-hot-toast'
import { dashboardApi, estimatesApi } from '../api/client'
import TopNav from '../components/TopNav'

const money = (n) => `₹${Number(n).toLocaleString('en-IN')}`
const fmtDate = (d) => new Date(d).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
const monthLabel = (d) => new Date(d).toLocaleDateString('en-IN', { month: 'short', year: '2-digit' })

const STATUS_ORDER = ['draft', 'sent', 'accepted', 'rejected']
const STATUS_COLORS = {
  draft: 'var(--c-text-muted)', sent: '#3b82f6', accepted: '#22c55e', rejected: '#ef4444',
  superseded: '#a855f7',
}

function EstimateRow({ est, onClick }) {
  return (
    <tr style={{ borderTop: '1px solid var(--c-border)', cursor: 'pointer' }} onClick={onClick}>
      <td style={{ padding: '10px 16px', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
        EST-{String(est.number).padStart(4, '0')}{est.revision > 1 ? ` rev ${est.revision}` : ''}
      </td>
      <td style={{ padding: '10px 16px' }}>{est.customer_name}</td>
      <td style={{ padding: '10px 16px', color: 'var(--c-text-muted)' }}>{est.title || '—'}</td>
      <td style={{ padding: '10px 16px' }}>
        <span className="badge" style={{
          textTransform: 'capitalize', color: STATUS_COLORS[est.status],
          border: `1px solid ${STATUS_COLORS[est.status]}`, background: 'transparent',
        }}>{est.status}</span>
        {est.is_expired && (
          <span className="badge" style={{ marginLeft: 6, color: '#f97316', border: '1px solid #f97316', background: 'transparent' }}>expired</span>
        )}
      </td>
      <td style={{ padding: '10px 16px', textAlign: 'right', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{money(est.grand_total)}</td>
      <td style={{ padding: '10px 16px', textAlign: 'right', color: 'var(--c-text-muted)', fontSize: '0.8125rem' }}>
        <span className="flex items-center gap-1" style={{ justifyContent: 'flex-end' }}><Clock size={11} /> {fmtDate(est.updated_at)}</span>
      </td>
    </tr>
  )
}

function EstimateTable({ estimates, navigate, emptyText }) {
  if (estimates.length === 0) {
    return <p className="text-muted" style={{ padding: '20px 16px' }}>{emptyText}</p>
  }
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <thead>
        <tr style={{ background: 'var(--c-surface-2)' }}>
          {['Estimate', 'Customer', 'Title', 'Status', 'Total', 'Updated'].map((h, i) => (
            <th key={h} style={{ textAlign: i >= 4 ? 'right' : 'left', padding: '9px 16px', fontSize: '0.72rem', textTransform: 'uppercase', color: 'var(--c-text-muted)' }}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {estimates.map((est) => (
          <EstimateRow key={est.id} est={est} onClick={() => navigate(`/estimates/${est.id}`)} />
        ))}
      </tbody>
    </table>
  )
}

export default function HomePage() {
  const navigate = useNavigate()
  const [metrics, setMetrics] = useState(null)
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null)
  const [searching, setSearching] = useState(false)

  useEffect(() => {
    dashboardApi.metrics()
      .then(({ data }) => setMetrics(data))
      .catch(() => toast.error('Failed to load dashboard'))
      .finally(() => setLoading(false))
  }, [])

  // Debounced global quote search — 300ms after typing stops (same pattern as CustomersPage).
  useEffect(() => {
    if (!query.trim()) { setResults(null); return }
    setSearching(true)
    const t = setTimeout(() => {
      estimatesApi.search({ q: query.trim(), limit: 20 })
        .then(({ data }) => setResults(data))
        .catch(() => toast.error('Search failed'))
        .finally(() => setSearching(false))
    }, 300)
    return () => clearTimeout(t)
  }, [query])

  if (loading) {
    return <div className="flex items-center justify-center" style={{ height: '100vh' }}><div className="spinner" style={{ width: 36, height: 36 }} /></div>
  }
  if (!metrics) return null

  const pipeline = Object.fromEntries(metrics.pipeline.map((p) => [p.status, p]))
  const maxRevenue = Math.max(1, ...metrics.monthly_revenue.map((m) => m.total))

  return (
    <div className="dashboard-layout">
      <TopNav />
      <main className="dashboard-main fade-in">
        <div className="flex items-center justify-between" style={{ marginBottom: 24 }}>
          <div>
            <h1 style={{ marginBottom: 4 }}>Dashboard</h1>
            <p>{metrics.active_customers} customer{metrics.active_customers === 1 ? '' : 's'} · {metrics.active_designs} design{metrics.active_designs === 1 ? '' : 's'}</p>
          </div>
          <div style={{ position: 'relative' }}>
            <Search size={15} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--c-text-dim)' }} />
            <input
              placeholder="Search quotes — number, title, customer…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              style={{ paddingLeft: 32, width: 300 }}
            />
          </div>
        </div>

        {results !== null ? (
          <div className="card" style={{ padding: 0, overflow: 'hidden', marginBottom: 24 }}>
            <div className="flex items-center justify-between" style={{ padding: '10px 16px' }}>
              <h2 style={{ margin: 0 }}>Search results</h2>
              {searching && <span className="spinner" style={{ width: 14, height: 14 }} />}
            </div>
            <EstimateTable estimates={results} navigate={navigate} emptyText="No quotes match." />
          </div>
        ) : (
          <>
            {/* Pipeline metric cards */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 12, marginBottom: 24 }}>
              {STATUS_ORDER.map((s) => {
                const m = pipeline[s] || { count: 0, total: 0 }
                return (
                  <div key={s} className="card" style={{ padding: 16, borderTop: `3px solid ${STATUS_COLORS[s]}` }}>
                    <div className="text-xs text-muted" style={{ textTransform: 'uppercase', letterSpacing: '0.04em' }}>{s}</div>
                    <div style={{ fontSize: '1.6rem', fontWeight: 700, margin: '2px 0' }}>{m.count}</div>
                    <div className="text-sm" style={{ fontFamily: 'var(--font-mono)', color: 'var(--c-text-muted)' }}>{money(m.total)}</div>
                  </div>
                )
              })}
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.6fr', gap: 16, marginBottom: 24, alignItems: 'start' }}>
              {/* Monthly accepted revenue — simple CSS bars, no chart dependency */}
              <div className="card" style={{ padding: 16 }}>
                <h2 style={{ marginBottom: 12 }}>Accepted revenue — last 6 months</h2>
                {metrics.monthly_revenue.length === 0 ? (
                  <p className="text-muted text-sm">No accepted quotes yet.</p>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {metrics.monthly_revenue.map((m) => (
                      <div key={m.month} className="flex items-center gap-2">
                        <span className="text-xs text-muted" style={{ width: 52, flexShrink: 0 }}>{monthLabel(m.month)}</span>
                        <div style={{ flex: 1, background: 'var(--c-surface-2)', borderRadius: 4, overflow: 'hidden' }}>
                          <div style={{
                            width: `${Math.max(2, (m.total / maxRevenue) * 100)}%`,
                            background: 'var(--c-brand)', height: 18, borderRadius: 4,
                          }} />
                        </div>
                        <span className="text-xs" style={{ fontFamily: 'var(--font-mono)', width: 90, textAlign: 'right', flexShrink: 0 }}>{money(m.total)}</span>
                      </div>
                    ))}
                  </div>
                )}
                <div className="flex gap-2" style={{ marginTop: 16 }}>
                  <button className="btn btn-secondary btn-sm w-full" onClick={() => navigate('/customers')}><Users size={14} /> Customers</button>
                  <button className="btn btn-secondary btn-sm w-full" onClick={() => navigate('/designs')}><LayoutGrid size={14} /> Designs</button>
                </div>
              </div>

              {/* Recent estimates */}
              <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                <div className="flex items-center gap-2" style={{ padding: '12px 16px' }}>
                  <FileText size={16} />
                  <h2 style={{ margin: 0 }}>Recent estimates</h2>
                </div>
                <EstimateTable estimates={metrics.recent_estimates} navigate={navigate}
                  emptyText="No estimates yet — create one from a customer page." />
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  )
}
