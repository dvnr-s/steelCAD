import { useState } from 'react'
import { X, AppWindow, DoorOpen } from 'lucide-react'
import toast from 'react-hot-toast'
import { designsApi } from '../api/client'
import { makeEmptyTree } from '../store/editorStore'
import DimensionInput from './DimensionInput'

export default function NewDesignModal({ onClose, onCreate }) {
  const [productType, setProductType] = useState('window')
  const [name, setName] = useState('')
  const [width, setWidth] = useState(5)
  const [height, setHeight] = useState(4)
  const [sectionSize, setSectionSize] = useState('5')
  const [gauge, setGauge] = useState('18G')
  const [loading, setLoading] = useState(false)

  // Switching product swaps in sensible default dimensions for that product.
  const pickProduct = (pt) => {
    setProductType(pt)
    if (pt === 'door') { setWidth(3.5); setHeight(7) }
    else { setWidth(5); setHeight(4) }
  }

  const handleCreate = async (e) => {
    e.preventDefault()
    if (!name.trim()) { toast.error('Design name is required'); return }
    if (width < 1 || height < 1) { toast.error('Dimensions must be at least 1ft'); return }

    setLoading(true)
    try {
      const tree = makeEmptyTree(name, Number(width), Number(height), sectionSize, gauge, productType)
      const { data } = await designsApi.create({
        name: name.trim(),
        productType,
        outerWidth: Number(width),
        outerHeight: Number(height),
        sectionSize,
        gauge,
        tree_json: tree,
      })
      toast.success(productType === 'door' ? 'Door created!' : 'Design created!')
      onCreate(data.id)
    } catch (err) {
      const detail = err.response?.data?.detail
      toast.error(typeof detail === 'string' ? detail : 'Failed to create design')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        background: 'rgba(0,0,0,0.7)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        backdropFilter: 'blur(4px)',
      }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="card fade-in modal-card" style={{ '--modal-w': '460px', padding: 28 }}>
        <div className="flex items-center justify-between" style={{ marginBottom: 24 }}>
          <h3>New Design</h3>
          <button className="btn btn-ghost btn-icon" onClick={onClose}><X size={18} /></button>
        </div>

        <form onSubmit={handleCreate} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div className="form-group">
            <label>Product</label>
            <div className="flex gap-2">
              <button type="button"
                className={`btn btn-sm w-full ${productType === 'window' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => pickProduct('window')}>
                <AppWindow size={14} /> Window
              </button>
              <button type="button"
                className={`btn btn-sm w-full ${productType === 'door' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => pickProduct('door')}>
                <DoorOpen size={14} /> Door
              </button>
            </div>
            {productType === 'door' && (
              <p className="text-xs text-muted" style={{ marginTop: 6, lineHeight: 1.5 }}>
                Door frame base sits in the concrete — priced as 2×height + width. Add side
                panels or a fanlight with splits after creating.
              </p>
            )}
          </div>

          <div className="form-group">
            <label>{productType === 'door' ? 'Door Name' : 'Design Name'}</label>
            <input
              type="text"
              placeholder="e.g. Main Window, Gate Design..."
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
              required
            />
          </div>

          <div className="flex gap-3">
            <div className="form-group" style={{ flex: 1 }}>
              <label>Width</label>
              <DimensionInput value={width} onCommit={(v) => setWidth(v)} title={'Decimal feet or ft-in (e.g. 5\'6")'} />
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label>Height</label>
              <DimensionInput value={height} onCommit={(v) => setHeight(v)} title={'Decimal feet or ft-in (e.g. 4\'6")'} />
            </div>
          </div>

          <div className="flex gap-3">
            <div className="form-group" style={{ flex: 1 }}>
              <label>Section Size</label>
              <select value={sectionSize} onChange={(e) => setSectionSize(e.target.value)}>
                <option value="5">5 inch</option>
                <option value="6">6 inch</option>
                <option value="10">10 inch</option>
              </select>
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label>Gauge</label>
              <select value={gauge} onChange={(e) => setGauge(e.target.value)}>
                <option value="18G">18G</option>
                <option value="16G">16G</option>
              </select>
            </div>
          </div>

          <div className="flex gap-2" style={{ marginTop: 8 }}>
            <button type="button" className="btn btn-secondary w-full" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary w-full" disabled={loading}>
              {loading ? <span className="spinner" /> : null}
              Create Design
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
