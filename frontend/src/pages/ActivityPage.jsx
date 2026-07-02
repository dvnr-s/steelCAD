import { useEffect, useState } from 'react'
import { Activity } from 'lucide-react'
import toast from 'react-hot-toast'
import { auditApi } from '../api/client'
import TopNav from '../components/TopNav'

function when(iso) {
  return new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

const ACTION_COLORS = {
  'estimate.create': '#22c55e', 'estimate.delete': '#ef4444', 'estimate.status': '#3b82f6',
  'customer.delete': '#ef4444', 'design.delete': '#ef4444', 'rate.update': '#f59e0b',
}

export default function ActivityPage() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    auditApi.list({ limit: 200 })
      .then(({ data }) => setRows(Array.isArray(data) ? data : []))
      .catch(() => toast.error('Failed to load activity'))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="dashboard-layout">
      <TopNav />
      <main className="dashboard-main fade-in">
        <div className="flex items-center gap-2" style={{ marginBottom: 6 }}>
          <Activity size={22} />
          <h1>Activity</h1>
        </div>
        <p style={{ marginBottom: 24 }}>Recent changes across estimates, customers, designs, and rates.</p>

        {loading ? (
          <div className="flex items-center justify-center" style={{ height: 240 }}><div className="spinner" style={{ width: 32, height: 32 }} /></div>
        ) : rows.length === 0 ? (
          <p className="text-muted">No activity recorded yet.</p>
        ) : (
          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: 'var(--c-surface-2)' }}>
                  {['When', 'Who', 'Action', 'Detail'].map((h) => (
                    <th key={h} style={{ textAlign: 'left', padding: '10px 16px', fontSize: '0.72rem', textTransform: 'uppercase', color: 'var(--c-text-muted)' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} style={{ borderTop: '1px solid var(--c-border)' }}>
                    <td style={{ padding: '10px 16px', color: 'var(--c-text-muted)', whiteSpace: 'nowrap' }}>{when(r.created_at)}</td>
                    <td style={{ padding: '10px 16px' }}>{r.actor_name}</td>
                    <td style={{ padding: '10px 16px' }}>
                      <span className="badge" style={{ color: ACTION_COLORS[r.action] || 'var(--c-text-muted)', border: `1px solid ${ACTION_COLORS[r.action] || 'var(--c-border-2)'}`, background: 'transparent', fontFamily: 'var(--font-mono)', fontSize: '0.72rem' }}>{r.action}</span>
                    </td>
                    <td style={{ padding: '10px 16px', color: 'var(--c-text-muted)' }}>{r.summary}</td>
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
