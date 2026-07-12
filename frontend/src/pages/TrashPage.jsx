/**
 * Trash — soft-deleted customers, designs, and estimates with restore buttons.
 * Admin/owner only (matches the delete/restore role gate on the backend).
 */
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Trash2, RotateCcw, Users, LayoutGrid, FileText } from 'lucide-react'
import toast from 'react-hot-toast'
import { trashApi, customersApi, designsApi, estimatesApi } from '../api/client'
import TopNav from '../components/TopNav'

const money = (n) => `₹${Number(n).toLocaleString('en-IN')}`
const fmtDate = (d) => new Date(d).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })

function Section({ icon, title, count, children }) {
  return (
    <div style={{ marginBottom: 28 }}>
      <div className="flex items-center gap-2" style={{ marginBottom: 10 }}>
        {icon}
        <h2 style={{ margin: 0 }}>{title}</h2>
        <span className="badge">{count}</span>
      </div>
      {count === 0 ? (
        <p className="text-muted text-sm">Nothing here.</p>
      ) : (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>{children}</div>
      )}
    </div>
  )
}

function Row({ children, onRestore, restoring, disabled, disabledReason }) {
  return (
    <div className="flex items-center justify-between" style={{ padding: '10px 16px', borderTop: '1px solid var(--c-border)' }}>
      <div style={{ minWidth: 0 }}>{children}</div>
      <button className="btn btn-secondary btn-sm" onClick={onRestore} disabled={restoring || disabled}
        title={disabled ? disabledReason : 'Restore'}>
        <RotateCcw size={14} /> Restore
      </button>
    </div>
  )
}

export default function TrashPage() {
  const navigate = useNavigate()
  const [trash, setTrash] = useState(null)
  const [loading, setLoading] = useState(true)
  const [restoring, setRestoring] = useState(false)

  const load = () => trashApi.list()
    .then(({ data }) => setTrash(data))
    .catch(() => toast.error('Failed to load trash'))
    .finally(() => setLoading(false))

  useEffect(() => { load() }, [])

  const restore = async (fn, label) => {
    setRestoring(true)
    try {
      await fn()
      toast.success(`${label} restored`)
      await load()
    } catch (err) {
      toast.error(err.response?.data?.detail || `Failed to restore ${label.toLowerCase()}`)
    } finally {
      setRestoring(false)
    }
  }

  if (loading) {
    return <div className="flex items-center justify-center" style={{ height: '100vh' }}><div className="spinner" style={{ width: 36, height: 36 }} /></div>
  }
  if (!trash) return null

  return (
    <div className="dashboard-layout">
      <TopNav />
      <main className="dashboard-main fade-in" style={{ maxWidth: 860 }}>
        <div className="flex items-center gap-2" style={{ marginBottom: 6 }}>
          <Trash2 size={22} />
          <h1>Trash</h1>
        </div>
        <p style={{ marginBottom: 24 }}>Deleted items are hidden but recoverable. Restoring brings them back exactly as they were.</p>

        <Section icon={<Users size={17} />} title="Customers" count={trash.customers.length}>
          {trash.customers.map((c) => (
            <Row key={c.id} restoring={restoring}
              onRestore={() => restore(() => customersApi.restore(c.id), 'Customer')}>
              <div style={{ fontWeight: 600 }}>{c.name}{c.company ? ` · ${c.company}` : ''}</div>
              <div className="text-xs text-muted">Deleted {fmtDate(c.deleted_at)}</div>
            </Row>
          ))}
        </Section>

        <Section icon={<LayoutGrid size={17} />} title="Designs" count={trash.designs.length}>
          {trash.designs.map((d) => (
            <Row key={d.id} restoring={restoring}
              onRestore={() => restore(() => designsApi.restore(d.id), 'Design')}>
              <div style={{ fontWeight: 600 }}>{d.name}</div>
              <div className="text-xs text-muted">Deleted {fmtDate(d.deleted_at)}</div>
            </Row>
          ))}
        </Section>

        <Section icon={<FileText size={17} />} title="Estimates" count={trash.estimates.length}>
          {trash.estimates.map((e) => (
            <Row key={e.id} restoring={restoring}
              disabled={e.customer_deleted}
              disabledReason="Restore the customer first"
              onRestore={() => restore(
                () => estimatesApi.restore(e.id).then(() => navigate(`/estimates/${e.id}`)),
                'Estimate',
              )}>
              <div style={{ fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                EST-{String(e.number).padStart(4, '0')}{e.revision > 1 ? ` rev ${e.revision}` : ''}
                <span style={{ fontFamily: 'var(--font-sans)', fontWeight: 400, color: 'var(--c-text-muted)' }}>
                  {' '}· {e.customer_name} · {money(e.grand_total)}
                </span>
              </div>
              <div className="text-xs text-muted">
                Deleted {fmtDate(e.deleted_at)}
                {e.customer_deleted && <span style={{ color: 'var(--c-error)' }}> — customer is deleted; restore the customer first</span>}
              </div>
            </Row>
          ))}
        </Section>
      </main>
    </div>
  )
}
