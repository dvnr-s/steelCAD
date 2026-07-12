import { useEffect, useState } from 'react'
import { Save, Building2, Upload, X } from 'lucide-react'
import toast from 'react-hot-toast'
import { settingsApi } from '../api/client'
import TopNav from '../components/TopNav'

const EMPTY = {
  name: '', logo_data_url: null, address: '', phone: '', email: '',
  gstin: '', bank_details: '', default_terms: '',
  gst_pct: 18, default_advance_pct: 50, currency_symbol: '₹',
}

const MAX_LOGO_BYTES = 250 * 1024  // keep the data-URL small enough to inline in the PDF

export default function SettingsPage() {
  const [form, setForm] = useState(EMPTY)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  useEffect(() => {
    settingsApi.getCompany()
      .then(({ data }) => setForm({ ...EMPTY, ...data }))
      .catch(() => toast.error('Failed to load company settings'))
      .finally(() => setLoading(false))
  }, [])

  const onLogo = (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (file.size > MAX_LOGO_BYTES) { toast.error('Logo must be under 250 KB'); return }
    const reader = new FileReader()
    reader.onload = () => setForm((f) => ({ ...f, logo_data_url: reader.result }))
    reader.readAsDataURL(file)
  }

  const save = async () => {
    if (!form.name.trim()) { toast.error('Company name is required'); return }
    const gst = Number(form.gst_pct)
    const adv = Number(form.default_advance_pct)
    if (Number.isNaN(gst) || gst < 0 || gst > 100) { toast.error('GST % must be between 0 and 100'); return }
    if (Number.isNaN(adv) || adv < 0 || adv > 100) { toast.error('Advance % must be between 0 and 100'); return }
    if (!String(form.currency_symbol || '').trim()) { toast.error('Currency symbol is required'); return }
    setSaving(true)
    try {
      const { data } = await settingsApi.updateCompany({ ...form, gst_pct: gst, default_advance_pct: adv })
      setForm({ ...EMPTY, ...data })
      toast.success('Company profile saved')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div className="flex items-center justify-center" style={{ height: '100vh' }}><div className="spinner" style={{ width: 36, height: 36 }} /></div>
  }

  return (
    <div className="dashboard-layout">
      <TopNav />
      <main className="dashboard-main fade-in" style={{ maxWidth: 720 }}>
        <div className="flex items-center gap-2" style={{ marginBottom: 6 }}>
          <Building2 size={22} />
          <h1>Company Profile</h1>
        </div>
        <p style={{ marginBottom: 24 }}>This information brands every quotation PDF — letterhead, GSTIN, terms, and bank details.</p>

        <div className="card" style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* Logo */}
          <div className="form-group">
            <label>Logo</label>
            <div className="flex items-center gap-3">
              {form.logo_data_url ? (
                <div className="flex items-center gap-2">
                  <img src={form.logo_data_url} alt="logo" style={{ maxHeight: 48, maxWidth: 140, border: '1px solid var(--c-border)', borderRadius: 6, padding: 4 }} />
                  <button className="btn btn-ghost btn-sm btn-icon" title="Remove logo" onClick={() => setForm((f) => ({ ...f, logo_data_url: null }))}><X size={15} /></button>
                </div>
              ) : <span className="text-muted text-sm">No logo uploaded</span>}
              <label className="btn btn-secondary btn-sm" style={{ cursor: 'pointer' }}>
                <Upload size={14} /> Upload
                <input type="file" accept="image/png,image/jpeg" onChange={onLogo} style={{ display: 'none' }} />
              </label>
            </div>
          </div>

          <div className="form-group">
            <label>Company name *</label>
            <input value={form.name} onChange={set('name')} placeholder="Acme Steel Works" />
          </div>
          <div className="flex gap-3">
            <div className="form-group" style={{ flex: 1 }}><label>Phone</label><input value={form.phone || ''} onChange={set('phone')} /></div>
            <div className="form-group" style={{ flex: 1 }}><label>Email</label><input value={form.email || ''} onChange={set('email')} /></div>
            <div className="form-group" style={{ flex: 1 }}><label>GSTIN</label><input value={form.gstin || ''} onChange={set('gstin')} /></div>
          </div>
          <div className="form-group"><label>Address</label><input value={form.address || ''} onChange={set('address')} placeholder="Street, city, state, PIN" /></div>
          <div className="form-group"><label>Bank details (for the PDF footer)</label><input value={form.bank_details || ''} onChange={set('bank_details')} placeholder="A/C name, number, IFSC, branch" /></div>
          <div className="form-group"><label>Default terms &amp; conditions</label><input value={form.default_terms || ''} onChange={set('default_terms')} placeholder="Used when an estimate has no terms of its own" /></div>

          {/* Commercial defaults */}
          <div style={{ height: 1, background: 'var(--c-border)' }} />
          <div>
            <label style={{ fontWeight: 600 }}>Commercial defaults</label>
            <p className="text-muted text-sm" style={{ margin: '2px 0 10px' }}>
              Applied to new estimates only — existing estimates keep the GST rate they were quoted at.
            </p>
            <div className="flex gap-3">
              <div className="form-group" style={{ flex: 1 }}>
                <label>GST %</label>
                <input type="number" min="0" max="100" step="0.5" value={form.gst_pct} onChange={set('gst_pct')} />
              </div>
              <div className="form-group" style={{ flex: 1 }}>
                <label>Default advance %</label>
                <input type="number" min="0" max="100" step="1" value={form.default_advance_pct} onChange={set('default_advance_pct')} />
              </div>
              <div className="form-group" style={{ flex: 1 }}>
                <label>Currency symbol</label>
                <input maxLength={8} value={form.currency_symbol || ''} onChange={set('currency_symbol')} placeholder="₹" />
              </div>
            </div>
          </div>

          <div className="flex justify-end">
            <button className="btn btn-primary" onClick={save} disabled={saving}>
              {saving ? <span className="spinner" style={{ width: 14, height: 14 }} /> : <Save size={15} />} Save Profile
            </button>
          </div>
        </div>
      </main>
    </div>
  )
}
