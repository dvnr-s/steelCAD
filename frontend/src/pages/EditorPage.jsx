/**
 * Editor page — the main design workspace.
 * Left: layer tree (future) | Center: Konva canvas | Right: properties panel
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Save, Check, Undo2, Redo2, AlertTriangle, CheckCircle2, SeparatorVertical, SeparatorHorizontal, MousePointer2, HelpCircle } from 'lucide-react'
import toast from 'react-hot-toast'
import useEditorStore from '../store/editorStore'
import { designsApi, estimatesApi, pricePreview } from '../api/client'
import { validateTree } from '../lib/validators'
import { useConfirm } from '../components/ConfirmModal'
import DesignCanvas from '../components/DesignCanvas'
import PropertiesPanel from '../components/PropertiesPanel'

function PriceDisplay({ price }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return
    const handler = (e) => { if (!ref.current?.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  if (!price) return null

  const fmt = (n) => `₹${(n ?? 0).toLocaleString('en-IN')}`
  const splitTotal = (price.splits ?? []).reduce((s, x) => s + (x.cost ?? 0), 0)
  const paneTotal = (price.regions ?? []).reduce((s, r) =>
    s + (r.pane_structure?.cost ?? 0) + (r.infill?.cost ?? 0) + (r.beading?.cost ?? 0) + (r.grill?.cost ?? 0), 0)
  const hwTotal = (price.regions ?? []).reduce((s, r) =>
    s + (r.hardware ?? []).reduce((a, h) => a + (h.cost ?? 0), 0), 0)

  const categories = [
    ['Frame', price.frame?.cost ?? 0],
    ['Splits', splitTotal],
    ['Pane / Glass', paneTotal],
    ['Hardware', hwTotal],
  ].filter(([, v]) => v > 0)

  return (
    <div ref={ref} style={{ position: 'relative', padding: '0 12px', borderLeft: '1px solid var(--c-border)' }}>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{ background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left', padding: 0 }}
        title="Click to see breakdown"
      >
        <div style={{ fontSize: '0.6875rem', color: 'var(--c-text-dim)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          Unit Subtotal {open ? '▲' : '▼'}
        </div>
        <div style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--c-brand)', fontFamily: 'var(--font-mono)' }}>
          {fmt(price.subtotal)}
        </div>
      </button>

      {open && (
        <div style={{
          position: 'absolute', top: 'calc(100% + 6px)', right: 0, zIndex: 100,
          background: 'var(--c-surface)', border: '1px solid var(--c-border)',
          borderRadius: 'var(--radius)', boxShadow: '0 4px 20px rgba(0,0,0,0.25)',
          padding: '12px 16px', minWidth: 240,
        }}>
          {categories.map(([label, val]) => (
            <div key={label} style={{ display: 'flex', justifyContent: 'space-between', gap: 32, padding: '3px 0', fontSize: '0.8125rem' }}>
              <span style={{ color: 'var(--c-text-muted)' }}>{label}</span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>{fmt(val)}</span>
            </div>
          ))}
          <div style={{ height: 1, background: 'var(--c-border)', margin: '8px 0' }} />
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 32, fontWeight: 700, fontSize: '0.875rem' }}>
            <span>Unit Subtotal</span>
            <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--c-brand)' }}>{fmt(price.subtotal)}</span>
          </div>
        </div>
      )}
    </div>
  )
}

function PricingBreakdown({ price }) {
  if (!price) return null
  const fmt = (n) => `₹${(n ?? 0).toLocaleString('en-IN')}`
  const dim = { fontSize: '0.75rem', color: 'var(--c-text-dim)' }
  const row = { display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8, padding: '2px 0', fontSize: '0.8125rem' }
  const mono = { fontFamily: 'var(--font-mono)' }
  const occupiedRegions = (price.regions ?? []).filter((r) => r.subtotal > 0)

  return (
    <div className="panel-section">
      <div className="panel-title">Pricing</div>

      {/* Frame */}
      <div style={{ marginBottom: 10 }}>
        <div style={{ ...dim, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 3 }}>Frame</div>
        <div style={row}>
          <span style={{ color: 'var(--c-text-muted)', fontSize: '0.8125rem' }}>{price.frame?.label}</span>
          <span style={mono}>{fmt(price.frame?.cost)}</span>
        </div>
        <div style={dim}>{price.frame?.quantity} RFT × ₹{price.frame?.rate}/RFT</div>
      </div>

      {/* Splits */}
      {(price.splits ?? []).length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ ...dim, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 3 }}>
            Splits ({price.splits.length})
          </div>
          {price.splits.map((s, i) => (
            <div key={i} style={row}>
              <span style={{ color: 'var(--c-text-muted)', display: 'flex', gap: 5, alignItems: 'center' }}>
                {s.label}
                <span style={{ ...dim }}>
                  {s.quantity} ft
                  <span style={{ marginLeft: 3, opacity: 0.8 }}>{s.double ? '×2' : '×1'}</span>
                </span>
              </span>
              <span style={mono}>{fmt(s.cost)}</span>
            </div>
          ))}
        </div>
      )}

      {/* Regions */}
      {occupiedRegions.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ ...dim, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 3 }}>Regions</div>
          {occupiedRegions.map((r, i) => (
            <div key={i} style={{ marginBottom: 6, paddingLeft: 6, borderLeft: '2px solid var(--c-border)' }}>
              <div style={{ ...row, fontWeight: 500 }}>
                <span style={{ display: 'flex', gap: 4, alignItems: 'baseline' }}>
                  {r.region_label}
                  <span style={dim}>{r.dimensions}</span>
                </span>
                <span style={mono}>{fmt(r.subtotal)}</span>
              </div>
              {r.pane_structure && <div style={{ ...row, ...dim }}><span>Pane</span><span>{fmt(r.pane_structure.cost)}</span></div>}
              {r.infill && <div style={{ ...row, ...dim }}><span>Infill</span><span>{fmt(r.infill.cost)}</span></div>}
              {r.beading && <div style={{ ...row, ...dim }}><span>Beading</span><span>{fmt(r.beading.cost)}</span></div>}
              {r.grill && <div style={{ ...row, ...dim }}><span>Grill</span><span>{fmt(r.grill.cost)}</span></div>}
              {(r.hardware ?? []).length > 0 && (
                <div style={{ ...row, ...dim }}>
                  <span>Hardware</span>
                  <span>{fmt(r.hardware.reduce((s, h) => s + (h.cost ?? 0), 0))}</span>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <div style={{ height: 1, background: 'var(--c-border)', margin: '6px 0' }} />
      <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 700, fontSize: '0.875rem' }}>
        <span>Unit Subtotal</span>
        <span style={{ ...mono, color: 'var(--c-brand)' }}>{fmt(price.subtotal)}</span>
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
  const selectedId = useEditorStore((s) => s.selectedId)
  const copyRegion = useEditorStore((s) => s.copyRegion)
  const pasteOnto = useEditorStore((s) => s.pasteOnto)

  const [loading, setLoading] = useState(!!id || frameMode)
  const [saving, setSaving] = useState(false)
  const [showHelp, setShowHelp] = useState(false)
  // Pricing fetch failed — the displayed price no longer matches the tree.
  const [priceStale, setPriceStale] = useState(false)
  const canvasRef = useRef(null)
  const [canvasSize, setCanvasSize] = useState({ width: 800, height: 600 })
  const { confirm, ConfirmDialog } = useConfirm()

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
      // Don't hijack typing in form fields.
      const tag = e.target?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      if (e.key === 'Escape') { setAddMode(null); setShowHelp(false); return }
      if (e.key === '?') { setShowHelp((v) => !v); return }
      const mod = e.ctrlKey || e.metaKey
      if (!mod) return
      const key = e.key.toLowerCase()
      if (key === 'z' && !e.shiftKey) {
        e.preventDefault()
        undo()
      } else if ((key === 'z' && e.shiftKey) || key === 'y') {
        e.preventDefault()
        redo()
      } else if (key === 'c' && selectedId) {
        if (copyRegion(selectedId)) { e.preventDefault(); toast.success('Region copied') }
      } else if (key === 'v' && selectedId) {
        if (pasteOnto(selectedId)) { e.preventDefault(); toast.success('Pasted onto region') }
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [undo, redo, setAddMode, selectedId, copyRegion, pasteOnto])

  // Warn on browser-level navigation (refresh / close / hard nav) with unsaved edits.
  useEffect(() => {
    if (!isDirty) return
    const onBeforeUnload = (e) => { e.preventDefault(); e.returnValue = '' }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [isDirty])

  // Refresh live unit price whenever tree changes (debounced).
  // On failure keep the last known price but flag it stale.
  const refreshPrice = useCallback(async () => {
    try {
      const { data } = await pricePreview(useEditorStore.getState().tree)
      setLivePrice(data)
      setPriceStale(false)
    } catch {
      setPriceStale(true)
    }
  }, [setLivePrice])

  const priceTimeout = useRef(null)
  useEffect(() => {
    if (!tree) return
    clearTimeout(priceTimeout.current)
    priceTimeout.current = setTimeout(refreshPrice, 600)
    return () => clearTimeout(priceTimeout.current)
  }, [tree, refreshPrice])

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

  const backTo = frameMode ? `/estimates/${estimateId}` : '/designs'
  const handleBack = async () => {
    if (isDirty) {
      const ok = await confirm('You have unsaved changes. Leave without saving?', {
        title: 'Unsaved changes', confirmLabel: 'Leave',
      })
      if (!ok) return
    }
    navigate(backTo)
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
      {ConfirmDialog}
      {showHelp && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 1100, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', backdropFilter: 'blur(4px)' }}
          onClick={() => setShowHelp(false)}>
          <div className="card" style={{ width: 380, padding: 24 }} onClick={(e) => e.stopPropagation()}>
            <h3 style={{ marginTop: 0, marginBottom: 14 }}>Keyboard shortcuts</h3>
            {[
              ['Ctrl/⌘ + Z', 'Undo'],
              ['Ctrl/⌘ + Shift + Z / Y', 'Redo'],
              ['Ctrl/⌘ + C', 'Copy selected region'],
              ['Ctrl/⌘ + V', 'Paste onto selected region'],
              ['Esc', 'Cancel tool / close'],
              ['?', 'Toggle this help'],
            ].map(([k, d]) => (
              <div key={k} className="flex items-center justify-between" style={{ padding: '5px 0', fontSize: '0.875rem' }}>
                <span style={{ color: 'var(--c-text-muted)' }}>{d}</span>
                <kbd style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', background: 'var(--c-surface-2)', border: '1px solid var(--c-border)', borderRadius: 4, padding: '2px 6px' }}>{k}</kbd>
              </div>
            ))}
          </div>
        </div>
      )}
      {/* Top bar */}
      <div className="editor-topbar">
        <button onClick={handleBack} className="btn btn-ghost btn-sm btn-icon" title="Back">
          <ArrowLeft size={17} />
        </button>

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

        {priceStale && (
          <button
            onClick={refreshPrice}
            title="Live pricing failed — the shown price may not match your latest edits. Click to retry."
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 4,
              padding: '2px 8px', marginRight: 8,
              fontSize: '0.6875rem', fontWeight: 600,
              color: '#92400e', background: '#fef3c7',
              border: '1px solid #fcd34d', borderRadius: 999, cursor: 'pointer',
            }}
          >
            price outdated — retry
          </button>
        )}
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
          <button
            className="btn btn-ghost btn-sm btn-icon"
            onClick={() => setShowHelp(true)}
            title="Keyboard shortcuts (?)"
          >
            <HelpCircle size={16} />
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

        {/* Live pricing breakdown */}
        <PricingBreakdown price={livePrice} />
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
