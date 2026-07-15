import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Trash2, BarChart3, Clock, Copy, Search } from 'lucide-react'
import toast from 'react-hot-toast'
import { designsApi } from '../api/client'
import { fmtFtIn } from '../lib/format'
import NewDesignModal from '../components/NewDesignModal'
import TopNav from '../components/TopNav'
import useThumbnail from '../hooks/useThumbnail'
import { useConfirm } from '../components/ConfirmModal'
import useAuthStore from '../store/authStore'

function formatDate(iso) {
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}

function DesignCard({ design, onDelete, onDuplicate, onOpen }) {
  const [deleting, setDeleting] = useState(false)
  const { confirm, ConfirmDialog } = useConfirm()
  const role = useAuthStore((s) => s.user?.role)
  const canDelete = role === 'admin' || role === 'owner'
  const thumbnail = useThumbnail(`/designs/${design.id}/thumbnail.svg?v=${encodeURIComponent(design.updated_at)}`)

  const handleDelete = async (e) => {
    e.stopPropagation()
    if (!await confirm(`Delete "${design.name}"? This cannot be undone.`, { title: 'Delete Design', confirmLabel: 'Delete' })) return
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
    <>
    {ConfirmDialog}
    <div className="design-card fade-in" onClick={() => onOpen(design.id)} role="button" tabIndex={0}>
      {/* Preview — server-rendered schematic; generic icon until it loads */}
      <div className="design-card-preview">
        {thumbnail ? (
          <img src={thumbnail} alt={`${design.name} schematic`}
            style={{ maxWidth: '100%', maxHeight: 120, objectFit: 'contain' }} />
        ) : (
          <svg width="80" height="60" viewBox="0 0 80 60" fill="none">
            <rect x="4" y="4" width="72" height="52" rx="3" stroke="var(--c-brand)" strokeWidth="2" opacity="0.6" />
            <rect x="12" y="4" width="1" height="52" fill="var(--c-brand)" opacity="0.3" />
            <rect x="40" y="4" width="1" height="52" fill="var(--c-brand)" opacity="0.3" />
            <rect x="4" y="28" width="72" height="1" fill="var(--c-brand)" opacity="0.3" />
          </svg>
        )}
      </div>

      {/* Info */}
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 600, marginBottom: 4, fontSize: '0.9375rem' }} className="truncate">
          {design.name}
        </div>
        <div className="flex gap-2" style={{ flexWrap: 'wrap' }}>
          {design.product_type === 'door' && <span className="badge" style={{ background: 'rgba(239,68,68,0.15)', color: '#ef4444' }}>Door</span>}
          <span className="badge badge-brand">{fmtFtIn(design.outer_width)} × {fmtFtIn(design.outer_height)}</span>
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
          onClick={(e) => { e.stopPropagation(); onDuplicate(design) }}
          title="Duplicate design"
        >
          <Copy size={14} />
        </button>
        {canDelete && (
          <button
            className="btn btn-ghost btn-sm btn-icon"
            onClick={handleDelete}
            disabled={deleting}
            title="Delete design"
            style={{ color: 'var(--c-error)' }}
          >
            {deleting ? <span className="spinner" style={{ width: 14, height: 14 }} /> : <Trash2 size={14} />}
          </button>
        )}
      </div>
    </div>
    </>
  )
}

export default function DashboardPage() {
  const navigate = useNavigate()

  const [designs, setDesigns] = useState([])
  const [loading, setLoading] = useState(true)
  const [showNewModal, setShowNewModal] = useState(false)
  const [query, setQuery] = useState('')

  const loadDesigns = async (q) => {
    try {
      const { data } = await designsApi.list({ limit: 50, q: q || undefined })
      setDesigns(data)
    } catch {
      toast.error('Failed to load designs')
    } finally {
      setLoading(false)
    }
  }

  // Debounced search.
  useEffect(() => {
    const t = setTimeout(() => loadDesigns(query.trim()), query ? 300 : 0)
    return () => clearTimeout(t)
  }, [query])

  const duplicateDesign = async (design) => {
    try {
      const { data: full } = await designsApi.get(design.id)
      await designsApi.create({
        name: `${full.name} (copy)`,
        description: full.description,
        outerWidth: full.outer_width,
        outerHeight: full.outer_height,
        sectionSize: full.section_size,
        gauge: full.gauge,
        tree_json: full.tree_json,
      })
      toast.success('Design duplicated')
      loadDesigns(query.trim())
    } catch {
      toast.error('Failed to duplicate design')
    }
  }

  return (
    <div className="dashboard-layout">
      <TopNav />

      {/* Main */}
      <main className="dashboard-main">
        {/* Header */}
        <div className="flex items-center justify-between" style={{ marginBottom: 28 }}>
          <div>
            <h1 style={{ marginBottom: 4 }}>Design Library</h1>
            <p>Reusable window & door designs — {designs.length} total. Add these to customer estimates as frames.</p>
          </div>
          <div className="flex items-center gap-2">
            <div style={{ position: 'relative' }}>
              <Search size={15} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--c-text-dim)' }} />
              <input
                placeholder="Search designs…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                style={{ paddingLeft: 32, width: 220 }}
              />
            </div>
            <button className="btn btn-primary" onClick={() => setShowNewModal(true)}>
              <Plus size={16} /> New Design
            </button>
          </div>
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
                onDuplicate={duplicateDesign}
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
