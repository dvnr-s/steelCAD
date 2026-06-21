import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Save } from 'lucide-react'
import toast from 'react-hot-toast'
import { ratesApi } from '../api/client'

const RATE_LABELS = {
  SECTION_5_18G: 'Section 5" 18G',
  SECTION_5_16G: 'Section 5" 16G',
  SECTION_6_18G: 'Section 6" 18G',
  SECTION_6_16G: 'Section 6" 16G',
  SECTION_10_18G: 'Section 10" 18G',
  SECTION_10_16G: 'Section 10" 16G',
  SHUTTER_MS_PIPE: 'Shutter — MS Pipe',
  SHUTTER_GP_SHEET: 'Shutter — GP Sheet',
  HINGE_SS_12G: 'Hinge — SS 12G',
  HINGE_SS_10G: 'Hinge — SS 10G',
  GRILL_MS_SQUARE: 'Grill — MS Square',
  GRILL_SS_PIPE_ROUND: 'Grill — SS Pipe Round',
  GRILL_SS_PIPE_SQUARE: 'Grill — SS Pipe Square',
  GLASS_BEADING: 'Glass Beading',
  JALI_WIRE_MESH: 'Jali Wire Mesh',
  LOCK_PROVISION: 'Lock Provision',
}

const GROUPS = {
  'Sections': ['SECTION_5_18G','SECTION_5_16G','SECTION_6_18G','SECTION_6_16G','SECTION_10_18G','SECTION_10_16G'],
  'Shutters': ['SHUTTER_MS_PIPE','SHUTTER_GP_SHEET'],
  'Hardware': ['HINGE_SS_12G','HINGE_SS_10G','LOCK_PROVISION'],
  'Grills': ['GRILL_MS_SQUARE','GRILL_SS_PIPE_ROUND','GRILL_SS_PIPE_SQUARE'],
  'Glass & Infill': ['GLASS_BEADING','JALI_WIRE_MESH'],
}

export default function RatesPage() {
  const navigate = useNavigate()
  const [rates, setRates] = useState({})
  const [edits, setEdits] = useState({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(null)

  useEffect(() => {
    ratesApi.list()
      .then(({ data }) => {
        const map = {}
        data.forEach((r) => { map[r.item_code] = r.rate })
        setRates(map)
        setEdits({ ...map })
      })
      .catch(() => toast.error('Failed to load rates'))
      .finally(() => setLoading(false))
  }, [])

  const handleSave = async (itemCode) => {
    const newRate = parseFloat(edits[itemCode])
    if (isNaN(newRate) || newRate <= 0) { toast.error('Rate must be > 0'); return }
    setSaving(itemCode)
    try {
      await ratesApi.update(itemCode, { rate: newRate })
      setRates((prev) => ({ ...prev, [itemCode]: newRate }))
      toast.success('Rate updated')
    } catch {
      toast.error('Failed to update rate')
    } finally {
      setSaving(null)
    }
  }

  const isDirty = (code) => edits[code] !== undefined && +edits[code] !== +rates[code]

  return (
    <div className="dashboard-layout">
      <nav className="dashboard-nav">
        <div className="flex items-center gap-3">
          <button className="btn btn-ghost btn-sm btn-icon" onClick={() => navigate('/')}>
            <ArrowLeft size={17} />
          </button>
          <h3 style={{ margin: 0 }}>Rate Management</h3>
          <span className="badge badge-accent">Admin Only</span>
        </div>
      </nav>

      <main className="dashboard-main fade-in">
        <div style={{ marginBottom: 24 }}>
          <h1 style={{ marginBottom: 8 }}>Material Rates</h1>
          <p>Update the per-unit rates used in estimate calculations. Changes apply to new estimates only — existing estimates are never affected.</p>
        </div>

        {loading ? (
          <div className="flex items-center justify-center" style={{ height: 300 }}>
            <div className="spinner" style={{ width: 32, height: 32 }} />
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {Object.entries(GROUPS).map(([group, codes]) => (
              <div key={group} className="card" style={{ padding: 0, overflow: 'hidden' }}>
                <div style={{
                  padding: '10px 16px',
                  background: 'var(--c-surface-2)',
                  borderBottom: '1px solid var(--c-border)',
                  fontWeight: 600,
                  fontSize: '0.875rem',
                }}>
                  {group}
                </div>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: 'left', padding: '8px 16px', fontSize: '0.75rem', fontWeight: 600, color: 'var(--c-text-muted)', textTransform: 'uppercase', borderBottom: '1px solid var(--c-border)' }}>Item</th>
                      <th style={{ textAlign: 'right', padding: '8px 16px', fontSize: '0.75rem', fontWeight: 600, color: 'var(--c-text-muted)', textTransform: 'uppercase', borderBottom: '1px solid var(--c-border)' }}>Rate (₹)</th>
                      <th style={{ width: 80, borderBottom: '1px solid var(--c-border)' }} />
                    </tr>
                  </thead>
                  <tbody>
                    {codes.filter((c) => rates[c] !== undefined || edits[c] !== undefined).map((code) => (
                      <tr key={code} style={{ borderBottom: '1px solid var(--c-border)' }}>
                        <td style={{ padding: '10px 16px', fontSize: '0.875rem' }}>
                          {RATE_LABELS[code] || code}
                        </td>
                        <td style={{ padding: '6px 16px', textAlign: 'right' }}>
                          <input
                            type="number"
                            min="1"
                            step="1"
                            value={edits[code] ?? rates[code] ?? ''}
                            onChange={(e) => setEdits((prev) => ({ ...prev, [code]: e.target.value }))}
                            style={{ width: 100, textAlign: 'right', fontFamily: 'var(--font-mono)' }}
                          />
                        </td>
                        <td style={{ padding: '6px 16px' }}>
                          <button
                            className="btn btn-primary btn-sm"
                            disabled={!isDirty(code) || saving === code}
                            onClick={() => handleSave(code)}
                          >
                            {saving === code ? <span className="spinner" style={{ width: 12, height: 12 }} /> : <Save size={12} />}
                            Save
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
