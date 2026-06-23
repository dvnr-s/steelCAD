import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Plus, FileText, Trash2, Clock } from 'lucide-react'
import toast from 'react-hot-toast'
import { customersApi, estimatesApi } from '../api/client'
import TopNav from '../components/TopNav'

function formatDate(iso) {
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}
const money = (n) => `₹${Number(n).toLocaleString('en-IN')}`

export default function CustomerDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [customer, setCustomer] = useState(null)
  const [estimates, setEstimates] = useState([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)

  const load = async () => {
    try {
      const [{ data: c }, { data: e }] = await Promise.all([
        customersApi.get(id),
        estimatesApi.listForCustomer(id),
      ])
      setCustomer(c)
      setEstimates(e)
    } catch {
      toast.error('Customer not found')
      navigate('/')
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { load() }, [id])

  const handleNewEstimate = async () => {
    setCreating(true)
    try {
      const { data } = await estimatesApi.create(id, { advance_pct: 50 })
      navigate(`/estimates/${data.id}`)
    } catch {
      toast.error('Failed to create estimate')
      setCreating(false)
    }
  }

  const handleDelete = async (e, est) => {
    e.stopPropagation()
    if (!confirm(`Delete estimate EST-${String(est.number).padStart(4, '0')}?`)) return
    try {
      await estimatesApi.delete(est.id)
      setEstimates((prev) => prev.filter((x) => x.id !== est.id))
      toast.success('Estimate deleted')
    } catch {
      toast.error('Failed to delete')
    }
  }

  if (loading) {
    return <div className="flex items-center justify-center" style={{ height: '100vh' }}><div className="spinner" style={{ width: 36, height: 36 }} /></div>
  }

  return (
    <div className="dashboard-layout">
      <TopNav />
      <main className="dashboard-main fade-in">
        <button className="btn btn-ghost btn-sm" onClick={() => navigate('/')} style={{ marginBottom: 16 }}>
          <ArrowLeft size={15} /> All customers
        </button>

        {/* Customer header */}
        <div className="card" style={{ padding: 20, marginBottom: 24 }}>
          <div className="flex items-start justify-between">
            <div>
              <h1 style={{ marginBottom: 6 }}>{customer.name}</h1>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, fontSize: '0.875rem', color: 'var(--c-text-muted)' }}>
                {customer.company && <span>{customer.company}</span>}
                {customer.phone && <span>{customer.phone}</span>}
                {customer.email && <span>{customer.email}</span>}
                {customer.gstin && <span>GSTIN: {customer.gstin}</span>}
              </div>
              {customer.address && <div style={{ marginTop: 8, fontSize: '0.875rem', color: 'var(--c-text-muted)' }}>{customer.address}</div>}
            </div>
          </div>
        </div>

        <div className="flex items-center justify-between" style={{ marginBottom: 16 }}>
          <h2>Estimates</h2>
          <button className="btn btn-primary" onClick={handleNewEstimate} disabled={creating}>
            {creating ? <span className="spinner" style={{ width: 14, height: 14 }} /> : <Plus size={16} />} New Estimate
          </button>
        </div>

        {estimates.length === 0 ? (
          <div className="flex flex-col items-center justify-center" style={{ height: 220, gap: 14 }}>
            <FileText size={28} color="var(--c-text-dim)" />
            <p>No estimates yet for this customer</p>
            <button className="btn btn-primary" onClick={handleNewEstimate} disabled={creating}><Plus size={16} /> Create First Estimate</button>
          </div>
        ) : (
          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: 'var(--c-surface-2)' }}>
                  <th style={{ textAlign: 'left', padding: '10px 16px', fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--c-text-muted)' }}>Estimate</th>
                  <th style={{ textAlign: 'left', padding: '10px 16px', fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--c-text-muted)' }}>Title</th>
                  <th style={{ textAlign: 'center', padding: '10px 16px', fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--c-text-muted)' }}>Frames</th>
                  <th style={{ textAlign: 'right', padding: '10px 16px', fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--c-text-muted)' }}>Grand Total</th>
                  <th style={{ textAlign: 'right', padding: '10px 16px', fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--c-text-muted)' }}>Date</th>
                  <th style={{ width: 50 }} />
                </tr>
              </thead>
              <tbody>
                {estimates.map((est) => (
                  <tr key={est.id} style={{ borderTop: '1px solid var(--c-border)', cursor: 'pointer' }} onClick={() => navigate(`/estimates/${est.id}`)}>
                    <td style={{ padding: '12px 16px', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                      EST-{String(est.number).padStart(4, '0')}
                      {est.status === 'final' && <span className="badge badge-brand" style={{ marginLeft: 8 }}>Final</span>}
                    </td>
                    <td style={{ padding: '12px 16px', color: 'var(--c-text-muted)' }}>{est.title || '—'}</td>
                    <td style={{ padding: '12px 16px', textAlign: 'center' }}>{est.frame_count}</td>
                    <td style={{ padding: '12px 16px', textAlign: 'right', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{money(est.grand_total)}</td>
                    <td style={{ padding: '12px 16px', textAlign: 'right', color: 'var(--c-text-muted)', fontSize: '0.8125rem' }}>
                      <span className="flex items-center gap-1" style={{ justifyContent: 'flex-end' }}><Clock size={11} /> {formatDate(est.updated_at)}</span>
                    </td>
                    <td style={{ padding: '8px 12px', textAlign: 'right' }}>
                      <button className="btn btn-ghost btn-sm btn-icon" style={{ color: 'var(--c-error)' }} onClick={(e) => handleDelete(e, est)} title="Delete estimate">
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  )
}
