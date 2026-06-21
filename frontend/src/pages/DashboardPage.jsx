import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, LogOut, Settings, Trash2, Pencil, BarChart3, Clock } from 'lucide-react'
import toast from 'react-hot-toast'
import useAuthStore from '../store/authStore'
import { designsApi } from '../api/client'
import NewDesignModal from '../components/NewDesignModal'

function formatDate(iso) {
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}

function DesignCard({ design, onDelete, onOpen }) {
  const [deleting, setDeleting] = useState(false)

  const handleDelete = async (e) => {
    e.stopPropagation()
    if (!confirm(`Delete "${design.name}"? This cannot be undone.`)) return
    setDeleting(true)
    try {
      await designsApi.delete(design.id)
      onDelete(design.id)
      toast.success('Design deleted')
    } catch {
      toast.error('Failed to delete design')
      setDeleting(false)
    }
  }

  return (
    <div className="design-card fade-in" onClick={() => onOpen(design.id)} role="button" tabIndex={0}>
      {/* Preview area — simple dimension icon */}
      <div className="design-card-preview">
        <svg width="80" height="60" viewBox="0 0 80 60" fill="none">
          <rect x="4" y="4" width="72" height="52" rx="3" stroke="var(--c-brand)" strokeWidth="2" opacity="0.6" />
          <rect x="12" y="4" width="1" height="52" fill="var(--c-brand)" opacity="0.3" />
          <rect x="40" y="4" width="1" height="52" fill="var(--c-brand)" opacity="0.3" />
          <rect x="4" y="28" width="72" height="1" fill="var(--c-brand)" opacity="0.3" />
        </svg>
      </div>

      {/* Info */}
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 600, marginBottom: 4, fontSize: '0.9375rem' }} className="truncate">
          {design.name}
        </div>
        <div className="flex gap-2" style={{ flexWrap: 'wrap' }}>
          <span className="badge badge-brand">{design.outer_width}ft × {design.outer_height}ft</span>
          <span className="badge badge-accent">{design.section_size}" {design.gauge}</span>
        </div>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between" style={{ marginTop: 4 }}>
        <div className="flex items-center gap-1 text-xs text-muted">
          <Clock size={11} />
          <span>{formatDate(design.updated_at)}</span>
        </div>
        <div className="flex items-center gap-1 text-xs text-muted">
          <span>By {design.created_by_name}</span>
        </div>
        <button
          className="btn btn-ghost btn-sm btn-icon"
          onClick={handleDelete}
          disabled={deleting}
          title="Delete design"
          style={{ color: 'var(--c-error)' }}
        >
          {deleting ? <span className="spinner" style={{ width: 14, height: 14 }} /> : <Trash2 size={14} />}
        </button>
      </div>
    </div>
  )
}

export default function DashboardPage() {
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const navigate = useNavigate()

  const [designs, setDesigns] = useState([])
  const [loading, setLoading] = useState(true)
  const [showNewModal, setShowNewModal] = useState(false)

  const loadDesigns = async () => {
    try {
      const { data } = await designsApi.list({ limit: 50 })
      setDesigns(data)
    } catch {
      toast.error('Failed to load designs')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadDesigns() }, [])

  const handleLogout = () => { logout(); navigate('/login') }

  return (
    <div className="dashboard-layout">
      {/* Nav */}
      <nav className="dashboard-nav">
        <div className="flex items-center gap-3">
          <div style={{
            width: 32, height: 32, background: 'var(--c-brand)',
            borderRadius: 7, display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <svg width="18" height="18" fill="none" viewBox="0 0 24 24" stroke="#fff" strokeWidth={2.5}>
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <path d="M3 9h18M9 21V9" />
            </svg>
          </div>
          <span style={{ fontWeight: 800, fontSize: '1.1rem', letterSpacing: '-0.02em' }}>SteelCAD</span>
        </div>

        <div className="flex items-center gap-2">
          {user?.is_admin && (
            <button className="btn btn-ghost btn-sm" onClick={() => navigate('/rates')}>
              <Settings size={15} /> Manage Rates
            </button>
          )}
          <div style={{
            padding: '4px 10px',
            background: 'var(--c-surface-2)',
            border: '1px solid var(--c-border)',
            borderRadius: 'var(--radius)',
            fontSize: '0.875rem',
          }}>
            {user?.name}
            {user?.is_admin && <span className="badge badge-accent" style={{ marginLeft: 6 }}>Admin</span>}
          </div>
          <button className="btn btn-ghost btn-sm btn-icon" onClick={handleLogout} title="Logout">
            <LogOut size={16} />
          </button>
        </div>
      </nav>

      {/* Main */}
      <main className="dashboard-main">
        {/* Header */}
        <div className="flex items-center justify-between" style={{ marginBottom: 28 }}>
          <div>
            <h1 style={{ marginBottom: 4 }}>Designs</h1>
            <p>All steel window & door designs — {designs.length} total</p>
          </div>
          <button className="btn btn-primary" onClick={() => setShowNewModal(true)}>
            <Plus size={16} /> New Design
          </button>
        </div>

        {/* Content */}
        {loading ? (
          <div className="flex items-center justify-center" style={{ height: 300 }}>
            <div className="spinner" style={{ width: 32, height: 32 }} />
          </div>
        ) : designs.length === 0 ? (
          <div className="flex flex-col items-center justify-center" style={{ height: 320, gap: 16 }}>
            <div style={{
              width: 72, height: 72, borderRadius: '50%',
              background: 'var(--c-surface-2)',
              border: '2px dashed var(--c-border-2)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <BarChart3 size={28} color="var(--c-text-dim)" />
            </div>
            <div style={{ textAlign: 'center' }}>
              <h3 style={{ marginBottom: 6 }}>No designs yet</h3>
              <p>Create your first steel window or door design</p>
            </div>
            <button className="btn btn-primary" onClick={() => setShowNewModal(true)}>
              <Plus size={16} /> Create First Design
            </button>
          </div>
        ) : (
          <div className="design-grid">
            {designs.map((d) => (
              <DesignCard
                key={d.id}
                design={d}
                onDelete={(id) => setDesigns((prev) => prev.filter((x) => x.id !== id))}
                onOpen={(id) => navigate(`/designs/${id}`)}
              />
            ))}
          </div>
        )}
      </main>

      {showNewModal && (
        <NewDesignModal
          onClose={() => setShowNewModal(false)}
          onCreate={(id) => navigate(`/designs/${id}`)}
        />
      )}
    </div>
  )
}
