import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Plus, Trash2, Pencil, Download, X, LayoutGrid, SquarePen, AppWindow, DoorOpen, Lock, Copy } from 'lucide-react'
import toast from 'react-hot-toast'
import { estimatesApi, designsApi } from '../api/client'
import { makeEmptyTree } from '../store/editorStore'
import TopNav from '../components/TopNav'
import { useConfirm } from '../components/ConfirmModal'

// Estimate lifecycle: only 'draft' is editable; the rest lock the estimate.
// 'superseded' is terminal (set only by Revise) and can't be picked manually.
const STATUS_OPTIONS = ['draft', 'sent', 'accepted', 'rejected']
const STATUS_COLORS = {
  draft: 'var(--c-text-muted)', sent: '#3b82f6', accepted: '#22c55e', rejected: '#ef4444',
  superseded: '#a855f7',
}

const money = (n) => `₹${Number(n).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const rupee = (n) => `₹${Number(n).toLocaleString('en-IN')}`

// ─── Add-frame modal ────────────────────────────────────────────────
function AddFrameModal({ estimateId, onClose, onAdded }) {
  const [tab, setTab] = useState('new')
  const [saving, setSaving] = useState(false)

  // library
  const [designs, setDesigns] = useState([])
  const [loadingLib, setLoadingLib] = useState(true)
  // new frame
  const [form, setForm] = useState({ name: '', width: 5, height: 4, sectionSize: '5', gauge: '18G', productType: 'window' })
  const [quantity, setQuantity] = useState(1)
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  // Switching product swaps in sensible default dimensions for that product.
  const pickProduct = (pt) =>
    setForm((f) => ({ ...f, productType: pt, ...(pt === 'door' ? { width: 3.5, height: 7 } : { width: 5, height: 4 }) }))

  useEffect(() => {
    designsApi.list({ limit: 100 }).then(({ data }) => setDesigns(data)).catch(() => {}).finally(() => setLoadingLib(false))
  }, [])

  const addFromLibrary = async (design) => {
    setSaving(true)
    try {
      const { data } = await estimatesApi.addFrame(estimateId, { source_design_id: design.id, quantity: Number(quantity) || 1 })
      toast.success(`Added "${design.name}"`)
      onAdded(data)
    } catch (err) {
      toast.error(err.response?.data?.detail?.validation_errors?.[0] || 'Failed to add frame')
      setSaving(false)
    }
  }

  const addNew = async (e) => {
    e.preventDefault()
    if (!form.name.trim()) { toast.error('Frame name is required'); return }
    setSaving(true)
    try {
      const tree = makeEmptyTree(form.name.trim(), Number(form.width), Number(form.height), form.sectionSize, form.gauge, form.productType)
      const { data } = await estimatesApi.addFrame(estimateId, { name: form.name.trim(), tree_json: tree, quantity: Number(quantity) || 1 })
      toast.success(form.productType === 'door' ? 'Door added — open it to design' : 'Frame added — open it to design')
      onAdded(data)
    } catch (err) {
      toast.error(err.response?.data?.detail?.validation_errors?.[0] || 'Failed to add frame')
      setSaving(false)
    }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', backdropFilter: 'blur(4px)' }}
      onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="card fade-in modal-card" style={{ '--modal-w': '520px', padding: 24, display: 'flex', flexDirection: 'column' }}>
        <div className="flex items-center justify-between" style={{ marginBottom: 16 }}>
          <h3>Add Frame</h3>
          <button className="btn btn-ghost btn-icon" onClick={onClose}><X size={18} /></button>
        </div>

        <div className="flex gap-2" style={{ marginBottom: 16 }}>
          <button className={`btn btn-sm w-full ${tab === 'new' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setTab('new')}>
            <SquarePen size={14} /> New Frame
          </button>
          <button className={`btn btn-sm w-full ${tab === 'library' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setTab('library')}>
            <LayoutGrid size={14} /> From Library
          </button>
        </div>

        <div className="form-group" style={{ marginBottom: 14 }}>
          <label>Quantity</label>
          <input type="number" min="1" value={quantity} onChange={(e) => setQuantity(e.target.value)} style={{ width: 110 }} />
        </div>

        {tab === 'new' ? (
          <form onSubmit={addNew} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div className="form-group">
              <label>Product</label>
              <div className="flex gap-2">
                <button type="button" className={`btn btn-sm w-full ${form.productType === 'window' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => pickProduct('window')}>
                  <AppWindow size={14} /> Window
                </button>
                <button type="button" className={`btn btn-sm w-full ${form.productType === 'door' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => pickProduct('door')}>
                  <DoorOpen size={14} /> Door
                </button>
              </div>
            </div>
            <div className="form-group">
              <label>{form.productType === 'door' ? 'Door Name' : 'Frame Name'}</label>
              <input value={form.name} onChange={set('name')} placeholder={form.productType === 'door' ? 'e.g. Main Entrance Door' : 'e.g. Living Room Window'} autoFocus required />
            </div>
            <div className="flex gap-3">
              <div className="form-group" style={{ flex: 1 }}><label>Width (ft)</label><input type="number" min="1" max="30" step="0.5" value={form.width} onChange={set('width')} /></div>
              <div className="form-group" style={{ flex: 1 }}><label>Height (ft)</label><input type="number" min="1" max="20" step="0.5" value={form.height} onChange={set('height')} /></div>
            </div>
            <div className="flex gap-3">
              <div className="form-group" style={{ flex: 1 }}>
                <label>Section</label>
                <select value={form.sectionSize} onChange={set('sectionSize')}><option value="5">5 inch</option><option value="6">6 inch</option><option value="10">10 inch</option></select>
              </div>
              <div className="form-group" style={{ flex: 1 }}>
                <label>Gauge</label>
                <select value={form.gauge} onChange={set('gauge')}><option value="18G">18G</option><option value="16G">16G</option></select>
              </div>
            </div>
            <button type="submit" className="btn btn-primary w-full" disabled={saving}>
              {saving ? <span className="spinner" /> : <Plus size={15} />} Add Frame
            </button>
          </form>
        ) : (
          <div style={{ overflowY: 'auto' }}>
            {loadingLib ? (
              <div className="flex items-center justify-center" style={{ height: 120 }}><div className="spinner" /></div>
            ) : designs.length === 0 ? (
              <p className="text-muted" style={{ textAlign: 'center', padding: 20 }}>No designs in the library yet.</p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {designs.map((d) => (
                  <button key={d.id} className="flex items-center justify-between" disabled={saving}
                    onClick={() => addFromLibrary(d)}
                    style={{ padding: '10px 12px', background: 'var(--c-surface-2)', border: '1px solid var(--c-border)', borderRadius: 'var(--radius)', cursor: 'pointer', textAlign: 'left' }}>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '0.875rem' }}>{d.name}</div>
                      <div className="text-xs text-muted">{d.outer_width}ft × {d.outer_height}ft · {d.section_size}" {d.gauge}</div>
                    </div>
                    <Plus size={16} color="var(--c-brand)" />
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Builder page ───────────────────────────────────────────────────
export default function EstimateBuilderPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [est, setEst] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [terms, setTerms] = useState({ title: '', notes: '', valid_until: '', terms: '', discount_type: '', discount_value: 0, advance_pct: 50, other_charges: [] })
  const { confirm, ConfirmDialog } = useConfirm()

  const locked = !!est && est.status !== 'draft'

  const applyEstimate = (data) => {
    setEst(data)
    setTerms({
      title: data.title || '', notes: data.notes || '',
      valid_until: data.valid_until || '', terms: data.terms || '',
      discount_type: data.discount_type || '', discount_value: data.discount_value || 0,
      advance_pct: data.advance_pct ?? 50,
      other_charges: data.other_charges || [],
    })
  }

  useEffect(() => {
    estimatesApi.get(id)
      .then(({ data }) => applyEstimate(data))
      .catch(() => { toast.error('Estimate not found'); navigate('/customers') })
      .finally(() => setLoading(false))
  }, [id])

  const changeStatus = async (status) => {
    try {
      const { data } = await estimatesApi.setStatus(id, status)
      applyEstimate(data)
      toast.success(`Marked ${status}`)
    } catch {
      toast.error('Failed to update status')
    }
  }

  const duplicateEstimate = async () => {
    try {
      const { data } = await estimatesApi.duplicate(id)
      toast.success(`Duplicated as EST-${String(data.number).padStart(4, '0')}`)
      navigate(`/estimates/${data.id}`)
    } catch {
      toast.error('Failed to duplicate estimate')
    }
  }

  const reviseEstimate = async () => {
    if (!await confirm(
      'Create a new revision? This quote becomes superseded (kept for history) and a fresh editable draft with the same number takes its place.',
      { title: 'Revise Quote', confirmLabel: 'Create Revision' },
    )) return
    try {
      const { data } = await estimatesApi.revise(id)
      toast.success(`Created EST-${String(data.number).padStart(4, '0')} rev ${data.revision}`)
      navigate(`/estimates/${data.id}`)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to revise estimate')
    }
  }

  const duplicateFrame = async (frameId) => {
    try {
      const { data } = await estimatesApi.duplicateFrame(id, frameId)
      applyEstimate(data)
      toast.success('Frame duplicated')
    } catch {
      toast.error('Failed to duplicate frame')
    }
  }

  const saveTerms = async (patch) => {
    try {
      const payload = { ...patch }
      if ('discount_type' in payload && payload.discount_type === '') payload.discount_type = null
      const { data } = await estimatesApi.update(id, payload)
      applyEstimate(data)
    } catch {
      toast.error('Failed to update estimate')
    }
  }

  // PR-9 other charges: rows without a label stay local-only (the backend
  // rejects empty labels), so a half-typed row survives the blur-save cycle.
  const setCharge = (i, patch) => setTerms((t) => ({
    ...t,
    other_charges: t.other_charges.map((c, j) => (j === i ? { ...c, ...patch } : c)),
  }))

  const saveCharges = (rows) => {
    const valid = rows
      .filter((c) => (c.label || '').trim())
      .map((c) => ({ label: c.label.trim(), amount: Math.max(0, Number(c.amount) || 0) }))
    if (JSON.stringify(valid) === JSON.stringify(est.other_charges || [])) return
    saveTerms({ other_charges: valid })
  }

  const removeCharge = (i) => {
    const rows = terms.other_charges.filter((_, j) => j !== i)
    setTerms((t) => ({ ...t, other_charges: rows }))
    saveCharges(rows)
  }

  const setFrameQty = async (frameId, qty) => {
    const q = Math.max(1, parseInt(qty, 10) || 1)
    try {
      const { data } = await estimatesApi.updateFrame(id, frameId, { quantity: q })
      applyEstimate(data)
    } catch {
      toast.error('Failed to update quantity')
    }
  }

  // Inline rename. Backend FrameUpdate.name; recompute refreshes the estimate.
  const setFrameName = async (frameId, name) => {
    const trimmed = (name || '').trim()
    if (!trimmed) { toast.error('Frame name cannot be empty'); return }
    try {
      const { data } = await estimatesApi.updateFrame(id, frameId, { name: trimmed })
      applyEstimate(data)
    } catch {
      toast.error('Failed to rename frame')
    }
  }

  // Section/gauge live in the geometry tree — patch tree_json so the backend
  // re-derives the frame columns and re-prices.
  const setFrameSpec = async (frame, patch) => {
    const tree = {
      ...frame.tree_json,
      sectionSize: patch.sectionSize ?? frame.section_size,
      gauge: patch.gauge ?? frame.gauge,
    }
    try {
      const { data } = await estimatesApi.updateFrame(id, frame.id, { tree_json: tree })
      applyEstimate(data)
    } catch {
      toast.error('Failed to update section')
    }
  }

  const deleteFrame = async (frameId) => {
    if (!await confirm('Remove this frame from the estimate?', { title: 'Remove Frame', confirmLabel: 'Remove' })) return
    try {
      const { data } = await estimatesApi.deleteFrame(id, frameId)
      applyEstimate(data)
      toast.success('Frame removed')
    } catch {
      toast.error('Failed to remove frame')
    }
  }

  const saveBlob = (data, type, filename) => {
    const url = URL.createObjectURL(new Blob([data], { type }))
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  const fileStem = () => `EST-${String(est.number).padStart(4, '0')}${est.revision > 1 ? `_rev${est.revision}` : ''}`

  const downloadPdf = async () => {
    setDownloading(true)
    try {
      const { data } = await estimatesApi.downloadPdf(id)
      saveBlob(data, 'application/pdf', `SteelCAD_${fileStem()}.pdf`)
    } catch {
      toast.error('PDF download failed')
    } finally {
      setDownloading(false)
    }
  }

  const downloadBom = async () => {
    try {
      const { data } = await estimatesApi.downloadBomCsv(id)
      saveBlob(data, 'text/csv', `SteelCAD_BOM_${fileStem()}.csv`)
    } catch {
      toast.error('BOM download failed')
    }
  }

  if (loading) {
    return <div className="flex items-center justify-center" style={{ height: '100vh' }}><div className="spinner" style={{ width: 36, height: 36 }} /></div>
  }
  if (!est) return null

  return (
    <div className="dashboard-layout">
      <TopNav />
      <main className="dashboard-main fade-in">
        <button className="btn btn-ghost btn-sm" onClick={() => navigate(`/customers/${est.customer.id}`)} style={{ marginBottom: 16 }}>
          <ArrowLeft size={15} /> {est.customer.name}
        </button>

        <div className="flex items-center justify-between" style={{ marginBottom: 20 }}>
          <div>
            <h1 style={{ marginBottom: 4 }}>
              Estimate EST-{String(est.number).padStart(4, '0')}
              {est.revision > 1 && <span style={{ color: 'var(--c-text-muted)', fontWeight: 500 }}> rev {est.revision}</span>}
            </h1>
            <p>For {est.customer.name}{est.customer.company ? ` · ${est.customer.company}` : ''}</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="badge" style={{
              textTransform: 'capitalize', color: STATUS_COLORS[est.status],
              border: `1px solid ${STATUS_COLORS[est.status]}`, background: 'transparent',
            }}>{est.status}</span>
            {est.is_expired && (
              <span className="badge" title="This sent quote is past its valid-until date — consider revising it"
                style={{ color: '#f97316', border: '1px solid #f97316', background: 'transparent' }}>
                expired
              </span>
            )}
            {est.status !== 'superseded' && (
              <select value={est.status} onChange={(e) => changeStatus(e.target.value)} title="Change status"
                style={{ width: 120, fontSize: '0.85rem', padding: '6px 8px' }}>
                {STATUS_OPTIONS.map((s) => (
                  <option key={s} value={s}>{s[0].toUpperCase() + s.slice(1)}</option>
                ))}
              </select>
            )}
            {locked && est.status !== 'superseded' && (
              <button className="btn btn-secondary" onClick={reviseEstimate}
                title="Create rev N+1 as a fresh draft; this quote becomes superseded">
                <Pencil size={15} /> Revise
              </button>
            )}
            <button className="btn btn-secondary" onClick={duplicateEstimate} title="Duplicate this estimate as a new draft with a new number">
              <Copy size={15} /> Duplicate
            </button>
            <button className="btn btn-secondary" onClick={downloadBom} disabled={est.frames.length === 0}
              title="Consolidated bill of materials as a spreadsheet">
              <Download size={15} /> BOM CSV
            </button>
            <button className="btn btn-primary" onClick={downloadPdf} disabled={downloading || est.frames.length === 0}>
              {downloading ? <span className="spinner" style={{ width: 14, height: 14 }} /> : <Download size={15} />} Download PDF
            </button>
          </div>
        </div>

        {est.status === 'superseded' ? (
          <div className="card" style={{ padding: '10px 14px', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8,
            borderLeft: `3px solid ${STATUS_COLORS.superseded}`, color: 'var(--c-text-muted)' }}>
            <Lock size={15} />
            <span>This revision was <strong>superseded</strong> by a newer one — it is kept read-only for history.
              Find the latest revision in the customer's estimate list.</span>
          </div>
        ) : locked && (
          <div className="card" style={{ padding: '10px 14px', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8,
            borderLeft: `3px solid ${STATUS_COLORS[est.status]}`, color: 'var(--c-text-muted)' }}>
            <Lock size={15} />
            <span>This estimate is <strong style={{ textTransform: 'capitalize' }}>{est.status}</strong> and locked.
              {est.is_expired && <> It expired on <strong>{est.valid_until}</strong> — consider revising it with fresh validity.</>}{' '}
              Use <strong>Revise</strong> to change what was quoted (keeps this version for history), or set status
              back to <strong>Draft</strong> only if it was sent by mistake.</span>
          </div>
        )}

        {/* Title + notes + quote details */}
        <div className="card" style={{ padding: 16, marginBottom: 20 }}>
          <div className="flex gap-3">
            <div className="form-group" style={{ flex: 1 }}>
              <label>Project title</label>
              <input value={terms.title} disabled={locked} onChange={(e) => setTerms((t) => ({ ...t, title: e.target.value }))} onBlur={() => saveTerms({ title: terms.title })} placeholder="e.g. Ground floor windows" />
            </div>
            <div className="form-group" style={{ flex: 2 }}>
              <label>Notes</label>
              <input value={terms.notes} disabled={locked} onChange={(e) => setTerms((t) => ({ ...t, notes: e.target.value }))} onBlur={() => saveTerms({ notes: terms.notes })} placeholder="Internal notes" />
            </div>
          </div>
          <div className="flex gap-3" style={{ marginTop: 12 }}>
            <div className="form-group" style={{ width: 200 }}>
              <label>Valid until</label>
              <input type="date" value={terms.valid_until || ''} disabled={locked}
                onChange={(e) => setTerms((t) => ({ ...t, valid_until: e.target.value }))}
                onBlur={() => saveTerms({ valid_until: terms.valid_until || null })} />
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label>Terms &amp; conditions (shown on the PDF)</label>
              <input value={terms.terms} disabled={locked} onChange={(e) => setTerms((t) => ({ ...t, terms: e.target.value }))} onBlur={() => saveTerms({ terms: terms.terms })} placeholder="Payment terms, delivery, warranty…" />
            </div>
          </div>
        </div>

        {/* Frames */}
        <div className="flex items-center justify-between" style={{ marginBottom: 12 }}>
          <h2>Frames</h2>
          <button className="btn btn-secondary btn-sm" onClick={() => setShowAdd(true)} disabled={locked}><Plus size={15} /> Add Frame</button>
        </div>

        <div className="card" style={{ padding: 0, overflow: 'hidden', marginBottom: 24 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: 'var(--c-surface-2)' }}>
                {['Frame', 'Dimensions', 'Section', 'Qty', 'Unit Price', 'Amount', ''].map((h, i) => (
                  <th key={i} style={{ textAlign: i >= 3 && i <= 5 ? 'right' : 'left', padding: '10px 16px', fontSize: '0.72rem', textTransform: 'uppercase', color: 'var(--c-text-muted)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {est.frames.length === 0 ? (
                <tr><td colSpan={7} style={{ textAlign: 'center', padding: 28, color: 'var(--c-text-muted)' }}>No frames yet — add a door or window to begin.</td></tr>
              ) : est.frames.map((f) => (
                <tr key={f.id} style={{ borderTop: '1px solid var(--c-border)' }}>
                  <td style={{ padding: '6px 16px', fontWeight: 600 }}>
                    <input
                      key={f.name}
                      defaultValue={f.name}
                      disabled={locked}
                      title="Click to rename"
                      onFocus={(e) => { e.target.style.borderColor = 'var(--c-border)' }}
                      onBlur={(e) => {
                        e.target.style.borderColor = 'transparent'
                        if (e.target.value.trim() !== f.name) setFrameName(f.id, e.target.value)
                      }}
                      style={{ fontWeight: 600, width: '100%', minWidth: 90, background: 'transparent', border: '1px solid transparent', borderRadius: 'var(--radius)', padding: '4px 6px' }}
                    />
                  </td>
                  <td style={{ padding: '10px 16px', color: 'var(--c-text-muted)', fontFamily: 'var(--font-mono)' }}>{f.outer_width}ft × {f.outer_height}ft</td>
                  <td style={{ padding: '6px 16px', color: 'var(--c-text-muted)' }}>
                    <div className="flex gap-1" style={{ alignItems: 'center' }}>
                      <select value={f.section_size} disabled={locked} onChange={(e) => setFrameSpec(f, { sectionSize: e.target.value })} title="Section size"
                        style={{ fontSize: '0.8rem', padding: '2px 4px', width: 58 }}>
                        <option value="5">5"</option>
                        <option value="6">6"</option>
                        <option value="10">10"</option>
                      </select>
                      <select value={f.gauge} disabled={locked} onChange={(e) => setFrameSpec(f, { gauge: e.target.value })} title="Gauge"
                        style={{ fontSize: '0.8rem', padding: '2px 4px', width: 64 }}>
                        <option value="18G">18G</option>
                        <option value="16G">16G</option>
                      </select>
                    </div>
                  </td>
                  <td style={{ padding: '6px 16px', textAlign: 'right' }}>
                    <input type="number" min="1" defaultValue={f.quantity} disabled={locked} onBlur={(e) => setFrameQty(f.id, e.target.value)}
                      style={{ width: 60, textAlign: 'right', fontFamily: 'var(--font-mono)' }} />
                  </td>
                  <td style={{ padding: '10px 16px', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{money(f.unit_subtotal)}</td>
                  <td style={{ padding: '10px 16px', textAlign: 'right', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{money(f.line_total)}</td>
                  <td style={{ padding: '6px 12px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                    <button className="btn btn-ghost btn-sm btn-icon" title={locked ? 'View design' : 'Edit design'} onClick={() => navigate(`/estimates/${id}/frames/${f.id}`)}><Pencil size={14} /></button>
                    <button className="btn btn-ghost btn-sm btn-icon" title="Duplicate frame" disabled={locked} onClick={() => duplicateFrame(f.id)}><Copy size={14} /></button>
                    <button className="btn btn-ghost btn-sm btn-icon" style={{ color: 'var(--c-error)' }} title="Remove" disabled={locked} onClick={() => deleteFrame(f.id)}><Trash2 size={14} /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Terms + totals */}
        <div className="flex gap-4" style={{ alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <div className="card" style={{ padding: 16, flex: 1, minWidth: 280 }}>
            <div className="panel-title" style={{ marginBottom: 12 }}>Commercial Terms</div>
            <div className="form-group" style={{ marginBottom: 10 }}>
              <label>Discount</label>
              <div className="flex gap-2">
                <select value={terms.discount_type} disabled={locked} onChange={(e) => { const v = e.target.value; setTerms((t) => ({ ...t, discount_type: v })); saveTerms({ discount_type: v, discount_value: terms.discount_value }) }} style={{ flex: 1 }}>
                  <option value="">None</option>
                  <option value="PERCENTAGE">Percentage (%)</option>
                  <option value="FLAT">Flat (₹)</option>
                </select>
                <input type="number" min="0" value={terms.discount_value} disabled={locked || !terms.discount_type}
                  onChange={(e) => setTerms((t) => ({ ...t, discount_value: e.target.value }))}
                  onBlur={() => saveTerms({ discount_value: Number(terms.discount_value) || 0 })}
                  style={{ width: 110, textAlign: 'right' }} />
              </div>
            </div>
            <div className="form-group" style={{ marginBottom: 10 }}>
              <label>Advance %</label>
              <input type="number" min="0" max="100" value={terms.advance_pct} disabled={locked}
                onChange={(e) => setTerms((t) => ({ ...t, advance_pct: e.target.value }))}
                onBlur={() => saveTerms({ advance_pct: Number(terms.advance_pct) || 0 })}
                style={{ width: 110, textAlign: 'right' }} />
            </div>
            <div className="form-group">
              <label>Other Charges (labor, transport, installation…)</label>
              {terms.other_charges.map((c, i) => (
                <div key={i} className="flex gap-2" style={{ marginBottom: 6 }}>
                  <input value={c.label} disabled={locked} placeholder="e.g. Transport"
                    onChange={(e) => setCharge(i, { label: e.target.value })}
                    onBlur={() => saveCharges(terms.other_charges)}
                    style={{ flex: 1 }} />
                  <input type="number" min="0" value={c.amount} disabled={locked}
                    onChange={(e) => setCharge(i, { amount: e.target.value })}
                    onBlur={() => saveCharges(terms.other_charges)}
                    style={{ width: 110, textAlign: 'right' }} />
                  {!locked && (
                    <button className="btn btn-ghost btn-icon" title="Remove charge" onClick={() => removeCharge(i)}>
                      <X size={14} />
                    </button>
                  )}
                </div>
              ))}
              {!locked && (
                <button className="btn btn-ghost btn-sm"
                  onClick={() => setTerms((t) => ({ ...t, other_charges: [...t.other_charges, { label: '', amount: 0 }] }))}>
                  <Plus size={14} /> Add charge
                </button>
              )}
            </div>
          </div>

          <div className="estimate-totals" style={{ flex: 1, minWidth: 300 }}>
            {[
              [(est.other_charges || []).length ? 'Subtotal (frames)' : 'Subtotal', money(est.subtotal)],
              ...(est.other_charges || []).map((c) => [c.label, money(c.amount)]),
              est.discount_amount > 0 && [`Discount${est.discount_type === 'PERCENTAGE' ? ` (${est.discount_value}%)` : ''}`, `− ${money(est.discount_amount)}`],
              ['Taxable Amount', money(est.taxable)],
              [`GST (${est.gst_pct ?? 18}%)`, money(est.gst)],
            ].filter(Boolean).map(([label, value], i) => (
              <div key={`${label}-${i}`} className="flex justify-between" style={{ padding: '10px 20px', borderBottom: '1px solid var(--c-border)' }}>
                <span style={{ fontWeight: 500 }}>{label}</span>
                <span className="font-mono">{value}</span>
              </div>
            ))}
            <div className="estimate-grand-total">
              <span>Grand Total</span>
              <span className="font-mono">{rupee(est.grand_total)}</span>
            </div>
            <div className="flex justify-between" style={{ padding: '12px 20px', background: 'var(--c-surface-3)' }}>
              <span style={{ fontWeight: 600, color: 'var(--c-accent)' }}>Advance ({est.advance_pct}%)</span>
              <span className="font-mono" style={{ fontWeight: 700, color: 'var(--c-accent)' }}>{rupee(est.advance_amount)}</span>
            </div>
          </div>
        </div>
      </main>

      {showAdd && (
        <AddFrameModal estimateId={id} onClose={() => setShowAdd(false)} onAdded={(data) => { applyEstimate(data); setShowAdd(false) }} />
      )}
      {ConfirmDialog}
    </div>
  )
}
