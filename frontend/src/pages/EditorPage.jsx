/**
 * Editor page — the main design workspace.
 * Left: layer tree (future) | Center: Konva canvas | Right: properties panel
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { ArrowLeft, Save, Check, Undo2, Redo2, AlertTriangle, CheckCircle2, SeparatorVertical, SeparatorHorizontal, MousePointer2 } from 'lucide-react'
import toast from 'react-hot-toast'
import useEditorStore from '../store/editorStore'
import { designsApi, estimatesApi, pricePreview } from '../api/client'
import { validateTree } from '../lib/validators'
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
          Unit Subtotal
        </div>
        <div style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--c-brand)', fontFamily: 'var(--font-mono)' }}>
          ₹{price.subtotal?.toLocaleString('en-IN')}
        </div>
      </div>
    </div>
  )
}

export default function EditorPage() {
  const { id, estimateId, frameId } = useParams()
  const navigate = useNavigate()
  const frameMode = !!frameId

  const tree = useEditorStore((s) => s.tree)
  const designId = useEditorStore((s) => s.designId)
  const designName = useEditorStore((s) => s.designName)
  const isDirty = useEditorStore((s) => s.isDirty)
  const livePrice = useEditorStore((s) => s.livePrice)
  const initTree = useEditorStore((s) => s.initTree)
  const setLivePrice = useEditorStore((s) => s.setLivePrice)
  const markSaved = useEditorStore((s) => s.markSaved)
  const undo = useEditorStore((s) => s.undo)
  const redo = useEditorStore((s) => s.redo)
  const canUndo = useEditorStore((s) => s.past.length > 0)
  const canRedo = useEditorStore((s) => s.future.length > 0)
  const addMode = useEditorStore((s) => s.addMode)
  const setAddMode = useEditorStore((s) => s.setAddMode)

  const [loading, setLoading] = useState(!!id || frameMode)
  const [saving, setSaving] = useState(false)
  const canvasRef = useRef(null)
  const [canvasSize, setCanvasSize] = useState({ width: 800, height: 600 })

  // Live design validation — mirrors backend rules for instant feedback.
  const issues = useMemo(() => (tree ? validateTree(tree) : []), [tree])
  const select = useEditorStore((s) => s.select)

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

  // Load existing design (library mode) or frame (estimate mode)
  useEffect(() => {
    if (frameMode) {
      setLoading(true)
      estimatesApi.get(estimateId)
        .then(({ data }) => {
          const frame = data.frames.find((f) => f.id === frameId)
          if (!frame) throw new Error('not found')
          initTree(frame.id, frame.tree_json)
        })
        .catch(() => {
          toast.error('Frame not found')
          navigate(`/estimates/${estimateId}`)
        })
        .finally(() => setLoading(false))
      return
    }
    if (!id) return
    setLoading(true)
    designsApi.get(id)
      .then(({ data }) => {
        initTree(data.id, data.tree_json)
      })
      .catch(() => {
        toast.error('Design not found')
        navigate('/designs')
      })
      .finally(() => setLoading(false))
  }, [id, frameId, estimateId])

  // Keyboard shortcuts — Ctrl/Cmd+Z undo, Ctrl/Cmd+Shift+Z or Ctrl+Y redo
  useEffect(() => {
    const onKeyDown = (e) => {
      if (e.key === 'Escape') { setAddMode(null); return }
      const mod = e.ctrlKey || e.metaKey
      if (!mod) return
      const key = e.key.toLowerCase()
      if (key === 'z' && !e.shiftKey) {
        e.preventDefault()
        undo()
      } else if ((key === 'z' && e.shiftKey) || key === 'y') {
        e.preventDefault()
        redo()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [undo, redo, setAddMode])

  // Refresh live unit price whenever tree changes (debounced)
  const priceTimeout = useRef(null)
  useEffect(() => {
    if (!tree) return
    clearTimeout(priceTimeout.current)
    priceTimeout.current = setTimeout(async () => {
      try {
        const { data } = await pricePreview(tree)
        setLivePrice(data)
      } catch {
        // silently ignore pricing errors during editing
      }
    }, 600)
    return () => clearTimeout(priceTimeout.current)
  }, [tree])

  const handleSave = async () => {
    if (!tree) return
    if (issues.length > 0) {
      toast.error(`Fix ${issues.length} issue${issues.length > 1 ? 's' : ''} before saving`)
      return
    }
    setSaving(true)
    try {
      if (frameMode) {
        await estimatesApi.updateFrame(estimateId, frameId, { name: designName, tree_json: tree })
        markSaved(frameId)
        toast.success('Frame saved')
      } else if (designId) {
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

  const handleDoneFrame = async () => {
    await handleSave()
    navigate(`/estimates/${estimateId}`)
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
        <Link to={frameMode ? `/estimates/${estimateId}` : '/designs'} className="btn btn-ghost btn-sm btn-icon" title="Back">
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

        <div className="flex gap-1" style={{ marginRight: 4 }}>
          <button
            className="btn btn-ghost btn-sm btn-icon"
            onClick={undo}
            disabled={!canUndo}
            title="Undo (Ctrl+Z)"
          >
            <Undo2 size={16} />
          </button>
          <button
            className="btn btn-ghost btn-sm btn-icon"
            onClick={redo}
            disabled={!canRedo}
            title="Redo (Ctrl+Shift+Z)"
          >
            <Redo2 size={16} />
          </button>
        </div>

        <div className="flex gap-2">
          <button
            className="btn btn-secondary btn-sm"
            onClick={handleSave}
            disabled={saving || !isDirty}
          >
            {saving ? <span className="spinner" style={{ width: 14, height: 14 }} /> : <Save size={14} />}
            Save
          </button>
          {frameMode && (
            <button
              className="btn btn-primary btn-sm"
              onClick={handleDoneFrame}
              disabled={saving}
              title="Save and return to estimate"
            >
              <Check size={14} /> Done
            </button>
          )}
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
            <strong>Drag</strong> a mullion to reposition (snaps to 3").<br />
            <strong>Double-click</strong> a mullion to remove it.<br />
            Use the <strong>V/H-Mullion</strong> tools to add splits.<br />
            Drag the blue <strong>frame handles</strong> to resize.<br />
            Click a region to edit type, pane, grill, hardware.
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
            {tree.productType === 'door' && (
              <div className="badge badge-accent" style={{ marginTop: 8 }}>
                Door · base in concrete (2×H + W)
              </div>
            )}
          </div>
        )}

        {/* Live validation */}
        {tree && (
          <div className="panel-section">
            <div className="panel-title">Validation</div>
            {issues.length === 0 ? (
              <div className="flex items-center gap-2" style={{ fontSize: '0.8125rem', color: 'var(--c-success, #22c55e)' }}>
                <CheckCircle2 size={15} /> No issues — ready to save
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {issues.map((issue, i) => (
                  <button
                    key={i}
                    onClick={() => issue.id && select(issue.id)}
                    className="flex items-start gap-2"
                    style={{
                      textAlign: 'left', background: 'transparent', border: 'none',
                      padding: '4px 0', cursor: issue.id ? 'pointer' : 'default',
                      fontSize: '0.8125rem', color: 'var(--c-warning, #f59e0b)', lineHeight: 1.4,
                    }}
                    title={issue.id ? 'Select this region' : ''}
                  >
                    <AlertTriangle size={14} style={{ flexShrink: 0, marginTop: 2 }} />
                    <span>{issue.message}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Center: canvas */}
      <div className="editor-canvas" ref={canvasRef} style={{ position: 'relative' }}>
        {/* Floating tool palette */}
        <div style={{
          position: 'absolute', top: 12, left: '50%', transform: 'translateX(-50%)',
          display: 'flex', gap: 4, padding: 4, zIndex: 10,
          background: 'var(--c-surface-2)', border: '1px solid var(--c-border)',
          borderRadius: 'var(--radius)', boxShadow: 'var(--shadow, 0 2px 8px rgba(0,0,0,0.2))',
        }}>
          <button
            className={`btn btn-sm ${!addMode ? 'btn-primary' : 'btn-ghost'}`}
            onClick={() => setAddMode(null)}
            title="Select / move (Esc)"
          >
            <MousePointer2 size={15} /> Select
          </button>
          <button
            className={`btn btn-sm ${addMode === 'vertical' ? 'btn-primary' : 'btn-ghost'}`}
            onClick={() => setAddMode(addMode === 'vertical' ? null : 'vertical')}
            title="Add vertical mullion — click a panel to place"
          >
            <SeparatorVertical size={15} /> V-Mullion
          </button>
          <button
            className={`btn btn-sm ${addMode === 'horizontal' ? 'btn-primary' : 'btn-ghost'}`}
            onClick={() => setAddMode(addMode === 'horizontal' ? null : 'horizontal')}
            title="Add horizontal mullion — click a panel to place"
          >
            <SeparatorHorizontal size={15} /> H-Mullion
          </button>
        </div>

        <DesignCanvas width={canvasSize.width} height={canvasSize.height} />
      </div>

      {/* Right: properties */}
      <div className="editor-right">
        <PropertiesPanel />
      </div>
    </div>
  )
}
