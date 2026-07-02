import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Trash2, Users, FileText, X, Phone, Building2, Search } from 'lucide-react'
import toast from 'react-hot-toast'
import { customersApi } from '../api/client'
import TopNav from '../components/TopNav'
import { useConfirm } from '../components/ConfirmModal'
import useAuthStore from '../store/authStore'

function NewCustomerModal({ onClose, onCreated }) {
  const [form, setForm] = useState({ name: '', company: '', phone: '', email: '', address: '', gstin: '' })
  const [saving, setSaving] = useState(false)
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault()
    if (!form.name.trim()) { toast.error('Customer name is required'); return }
    setSaving(true)
    try {
      const payload = Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v.trim() || null]))
      payload.name = form.name.trim()
      const { data } = await customersApi.create(payload)
      toast.success('Customer added')
      onCreated(data)
    } catch {
      toast.error('Failed to add customer')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', backdropFilter: 'blur(4px)' }}
      onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="card fade-in" style={{ width: 480, padding: 28 }}>
        <div className="flex items-center justify-between" style={{ marginBottom: 20 }}>
          <h3>New Customer</h3>
          <button className="btn btn-ghost btn-icon" onClick={onClose}><X size={18} /></button>
        </div>
        <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div className="form-group">
            <label>Name *</label>
            <input value={form.name} onChange={set('name')} autoFocus placeholder="e.g. Rajesh Kumar" required />
          </div>
          <div className="flex gap-3">
            <div className="form-group" style={{ flex: 1 }}><label>Company</label><input value={form.company} onChange={set('company')} /></div>
            <div className="form-group" style={{ flex: 1 }}><label>Phone</label><input value={form.phone} onChange={set('phone')} /></div>
          </div>
          <div className="form-group"><label>Email</label><input type="email" value={form.email} onChange={set('email')} /></div>
          <div className="form-group"><label>Address</label><input value={form.address} onChange={set('address')} /></div>
          <div className="form-group"><label>GSTIN</label><input value={form.gstin} onChange={set('gstin')} /></div>
          <div className="flex gap-2" style={{ marginTop: 6 }}>
            <button type="button" className="btn btn-secondary w-full" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary w-full" disabled={saving}>
              {saving ? <span className="spinner" /> : null} Add Customer
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function CustomersPage() {
  const navigate = useNavigate()
  const [customers, setCustomers] = useState([])
  const [loading, setLoading] = useState(true)
  const [showNew, setShowNew] = useState(false)
  const [query, setQuery] = useState('')
  const { confirm, ConfirmDialog } = useConfirm()
  const role = useAuthStore((s) => s.user?.role)
  const canDelete = role === 'admin' || role === 'owner'

  const load = async (q) => {
    try {
      const { data } = await customersApi.list({ limit: 100, q: q || undefined })
      setCustomers(Array.isArray(data) ? data : [])
    } catch {
      toast.error('Failed to load customers')
    } finally {
      setLoading(false)
    }
  }
  // Debounced search — refetch 300ms after the user stops typing.
  useEffect(() => {
    const t = setTimeout(() => load(query.trim()), query ? 300 : 0)
    return () => clearTimeout(t)
  }, [query])

  const handleDelete = async (e, c) => {
    e.stopPropagation()
    if (!await confirm(`Delete "${c.name}" and all their estimates? This cannot be undone.`, { title: 'Delete Customer', confirmLabel: 'Delete' })) return
    try {
      await customersApi.delete(c.id)
      setCustomers((prev) => prev.filter((x) => x.id !== c.id))
      toast.success('Customer deleted')
    } catch {
      toast.error('Failed to delete')
    }
  }

  return (
    <>
    {ConfirmDialog}
    <div className="dashboard-layout">
      <TopNav />
      <main className="dashboard-main">
        <div className="flex items-center justify-between" style={{ marginBottom: 28 }}>
          <div>
            <h1 style={{ marginBottom: 4 }}>Customers</h1>
            <p>{customers.length} customer{customers.length === 1 ? '' : 's'}{query ? ' matching' : ''}</p>
          </div>
          <div className="flex items-center gap-2">
            <div style={{ position: 'relative' }}>
              <Search size={15} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--c-text-dim)' }} />
              <input
                placeholder="Search name, company, phone…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                style={{ paddingLeft: 32, width: 240 }}
              />
            </div>
          <button className="btn btn-primary" onClick={() => setShowNew(true)}>
            <Plus size={16} /> New Customer
          </button>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center" style={{ height: 280 }}>
            <div className="spinner" style={{ width: 32, height: 32 }} />
          </div>
        ) : customers.length === 0 ? (
          <div className="flex flex-col items-center justify-center" style={{ height: 300, gap: 16 }}>
            <div style={{ width: 72, height: 72, borderRadius: '50%', background: 'var(--c-surface-2)', border: '2px dashed var(--c-border-2)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Users size={28} color="var(--c-text-dim)" />
            </div>
            <div style={{ textAlign: 'center' }}>
              <h3 style={{ marginBottom: 6 }}>No customers yet</h3>
              <p>Add a customer to start building estimates</p>
            </div>
            <button className="btn btn-primary" onClick={() => setShowNew(true)}><Plus size={16} /> Add First Customer</button>
          </div>
        ) : (
          <div className="design-grid">
            {customers.map((c) => (
              <div key={c.id} className="design-card fade-in" onClick={() => navigate(`/customers/${c.id}`)} role="button" tabIndex={0}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, fontSize: '1rem', marginBottom: 6 }} className="truncate">{c.name}</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: '0.8125rem', color: 'var(--c-text-muted)' }}>
                    {c.company && <span className="flex items-center gap-2"><Building2 size={13} /> {c.company}</span>}
                    {c.phone && <span className="flex items-center gap-2"><Phone size={13} /> {c.phone}</span>}
                  </div>
                </div>
                <div className="flex items-center justify-between" style={{ marginTop: 10 }}>
                  <span className="badge badge-brand flex items-center gap-1"><FileText size={11} /> {c.estimate_count} estimate{c.estimate_count === 1 ? '' : 's'}</span>
                  {canDelete && (
                    <button className="btn btn-ghost btn-sm btn-icon" style={{ color: 'var(--c-error)' }} onClick={(e) => handleDelete(e, c)} title="Delete customer">
                      <Trash2 size={14} />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </main>

      {showNew && (
        <NewCustomerModal
          onClose={() => setShowNew(false)}
          onCreated={(c) => { setShowNew(false); navigate(`/customers/${c.id}`) }}
        />
      )}
    </div>
    </>
  )
}
