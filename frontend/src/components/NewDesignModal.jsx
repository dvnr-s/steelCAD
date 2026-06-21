import { useState } from 'react'
import { X } from 'lucide-react'
import toast from 'react-hot-toast'
import { designsApi } from '../api/client'
import { makeEmptyTree } from '../store/editorStore'

export default function NewDesignModal({ onClose, onCreate }) {
  const [name, setName] = useState('')
  const [width, setWidth] = useState(5)
  const [height, setHeight] = useState(4)
  const [sectionSize, setSectionSize] = useState('5')
  const [gauge, setGauge] = useState('18G')
  const [loading, setLoading] = useState(false)

  const handleCreate = async (e) => {
    e.preventDefault()
    if (!name.trim()) { toast.error('Design name is required'); return }
    if (width < 1 || height < 1) { toast.error('Dimensions must be at least 1ft'); return }

    setLoading(true)
    try {
      const tree = makeEmptyTree(name, Number(width), Number(height), sectionSize, gauge)
      const { data } = await designsApi.create({
        name: name.trim(),
        outerWidth: Number(width),
        outerHeight: Number(height),
        sectionSize,
        gauge,
        tree_json: tree,
      })
      toast.success('Design created!')
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
      <div className="card fade-in" style={{ width: 460, padding: 28 }}>
        <div className="flex items-center justify-between" style={{ marginBottom: 24 }}>
          <h3>New Design</h3>
          <button className="btn btn-ghost btn-icon" onClick={onClose}><X size={18} /></button>
        </div>

        <form onSubmit={handleCreate} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div className="form-group">
            <label>Design Name</label>
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
              <label>Width (ft)</label>
              <input type="number" min="1" max="30" step="0.5" value={width}
                onChange={(e) => setWidth(e.target.value)} required />
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label>Height (ft)</label>
              <input type="number" min="1" max="20" step="0.5" value={height}
                onChange={(e) => setHeight(e.target.value)} required />
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
