/**
 * Editor page — the main design workspace.
 * Left: layer tree (future) | Center: Konva canvas | Right: properties panel
 */
import { useEffect, useRef, useState, useCallback } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { ArrowLeft, Save, Calculator, Download, RefreshCw } from 'lucide-react'
import toast from 'react-hot-toast'
import useEditorStore from '../store/editorStore'
import useAuthStore from '../store/authStore'
import { designsApi, estimatesApi } from '../api/client'
import DesignCanvas from '../components/DesignCanvas'
import PropertiesPanel from '../components/PropertiesPanel'

function PriceDisplay({ price }) {
  if (!price) return null
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12,
      padding: '0 12px',
      borderLeft: '1px solid var(--c-border)',
    }}>
      <div>
        <div style={{ fontSize: '0.6875rem', color: 'var(--c-text-dim)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          Live Estimate
        </div>
        <div style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--c-brand)', fontFamily: 'var(--font-mono)' }}>
          ₹{price.grand_total?.toLocaleString('en-IN')}
        </div>
      </div>
    </div>
  )
}

export default function EditorPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)

  const tree = useEditorStore((s) => s.tree)
  const designId = useEditorStore((s) => s.designId)
  const designName = useEditorStore((s) => s.designName)
  const isDirty = useEditorStore((s) => s.isDirty)
  const livePrice = useEditorStore((s) => s.livePrice)
  const initTree = useEditorStore((s) => s.initTree)
  const setLivePrice = useEditorStore((s) => s.setLivePrice)
  const markSaved = useEditorStore((s) => s.markSaved)

  const [loading, setLoading] = useState(!!id)
  const [saving, setSaving] = useState(false)
  const [generating, setGenerating] = useState(false)
  const canvasRef = useRef(null)
  const [canvasSize, setCanvasSize] = useState({ width: 800, height: 600 })

  // Track canvas size
  useEffect(() => {
    if (!canvasRef.current) return
    const ro = new ResizeObserver((entries) => {
      const entry = entries[0]
      setCanvasSize({ width: entry.contentRect.width, height: entry.contentRect.height })
    })
    ro.observe(canvasRef.current)
    return () => ro.disconnect()
  }, [])

  // Load existing design
  useEffect(() => {
    if (!id) return
    setLoading(true)
    designsApi.get(id)
      .then(({ data }) => {
        initTree(data.id, data.tree_json)
      })
      .catch(() => {
        toast.error('Design not found')
        navigate('/')
      })
      .finally(() => setLoading(false))
  }, [id])

  // Refresh live price whenever tree changes (debounced 1s)
  const priceTimeout = useRef(null)
  useEffect(() => {
    if (!tree || !designId) return
    clearTimeout(priceTimeout.current)
    priceTimeout.current = setTimeout(async () => {
      try {
        const { data } = await estimatesApi.create(designId, {})
        setLivePrice(data.breakdown)
      } catch {
        // silently ignore pricing errors during editing
      }
    }, 1000)
    return () => clearTimeout(priceTimeout.current)
  }, [tree, designId])

  const handleSave = async () => {
    if (!tree) return
    setSaving(true)
    try {
      if (designId) {
        await designsApi.update(designId, { name: designName, tree_json: tree })
        markSaved(designId)
        toast.success('Design saved')
      }
    } catch (err) {
      const detail = err.response?.data?.detail
      if (detail?.validation_errors) {
        toast.error(`Validation: ${detail.validation_errors[0]}`)
      } else {
        toast.error('Save failed')
      }
    } finally {
      setSaving(false)
    }
  }

  const handleGenerateEstimate = async () => {
    if (!designId) { toast.error('Save the design first'); return }
    setGenerating(true)
    try {
      const { data } = await estimatesApi.create(designId, {})
      toast.success(`Estimate v${data.version_number} created — ₹${data.breakdown.grand_total?.toLocaleString('en-IN')}`)
      navigate(`/estimates/${data.id}`)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to generate estimate')
    } finally {
      setGenerating(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center" style={{ height: '100vh' }}>
        <div className="spinner" style={{ width: 36, height: 36 }} />
      </div>
    )
  }

  return (
    <div className="editor-layout">
      {/* Top bar */}
      <div className="editor-topbar">
        <Link to="/" className="btn btn-ghost btn-sm btn-icon" title="Back to dashboard">
          <ArrowLeft size={17} />
        </Link>

        <div style={{ flex: 1 }}>
          <span style={{ fontWeight: 600, fontSize: '0.9375rem' }}>{designName}</span>
          {isDirty && (
            <span style={{
              marginLeft: 8, fontSize: '0.75rem',
              color: 'var(--c-accent)', fontWeight: 500,
            }}>
              • unsaved
            </span>
          )}
        </div>

        <PriceDisplay price={livePrice} />

        <div className="flex gap-2">
          <button
            className="btn btn-secondary btn-sm"
            onClick={handleSave}
            disabled={saving || !isDirty}
          >
            {saving ? <span className="spinner" style={{ width: 14, height: 14 }} /> : <Save size={14} />}
            Save
          </button>
          <button
            className="btn btn-primary btn-sm"
            onClick={handleGenerateEstimate}
            disabled={generating || isDirty}
            title={isDirty ? 'Save first to generate estimate' : ''}
          >
            {generating ? <span className="spinner" style={{ width: 14, height: 14 }} /> : <Calculator size={14} />}
            Estimate
          </button>
        </div>
      </div>

      {/* Left: region legend */}
      <div className="editor-left">
        <div className="panel-section">
          <div className="panel-title">Legend</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: '0.8125rem' }}>
            {[
              ['Open',    '#8b949e'],
              ['Fixed',   '#22c55e'],
              ['Shutter', '#f59e0b'],
              ['Door',    '#ef4444'],
              ['Louver',  '#8b5cf6'],
            ].map(([label, color]) => (
              <div key={label} className="flex items-center gap-2">
                <div style={{ width: 10, height: 10, borderRadius: 2, background: color }} />
                <span className="text-muted">{label}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="panel-section">
          <div className="panel-title">Canvas</div>
          <div style={{ fontSize: '0.8125rem', color: 'var(--c-text-muted)', lineHeight: 1.6 }}>
            Click a region to select.<br />
            Use the right panel to configure type, pane, grill, and hardware.
          </div>
        </div>

        {tree && (
          <div className="panel-section">
            <div className="panel-title">Size</div>
            <div style={{ fontSize: '0.875rem', fontFamily: 'var(--font-mono)', color: 'var(--c-text)' }}>
              {tree.outerWidth}ft × {tree.outerHeight}ft<br />
              <span style={{ color: 'var(--c-text-muted)', fontSize: '0.8125rem' }}>
                Section {tree.sectionSize}" {tree.gauge}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Center: canvas */}
      <div className="editor-canvas" ref={canvasRef}>
        <DesignCanvas width={canvasSize.width} height={canvasSize.height} />
      </div>

      {/* Right: properties */}
      <div className="editor-right">
        <PropertiesPanel />
      </div>
    </div>
  )
}
