/**
 * Shared top navigation bar.
 */
import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { LogOut, Settings, Users, LayoutGrid, UserCog, Building2, KeyRound, X, Activity, Trash2, LayoutDashboard, UserX } from 'lucide-react'
import toast from 'react-hot-toast'
import useAuthStore from '../store/authStore'
import { authApi } from '../api/client'

const ROLE_LABELS = { admin: 'Admin', owner: 'Owner', sales: 'Sales' }
const ROLE_BADGE_STYLE = {
  admin: { background: 'var(--c-brand)', color: '#fff' },
  owner: { background: 'var(--c-success)', color: '#fff' },
  sales: { background: 'var(--c-surface-3)', color: 'var(--c-text-muted)' },
}

function ChangePasswordModal({ onClose }) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [saving, setSaving] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    if (next.length < 8) { toast.error('New password must be at least 8 characters'); return }
    setSaving(true)
    try {
      await authApi.changePassword({ current_password: current, new_password: next })
      toast.success('Password updated')
      onClose()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to change password')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 1100, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', backdropFilter: 'blur(4px)' }}
      onClick={(e) => e.target === e.currentTarget && onClose()}>
      <form className="card fade-in modal-card" style={{ '--modal-w': '380px', padding: 24 }} onSubmit={submit}>
        <div className="flex items-center justify-between" style={{ marginBottom: 16 }}>
          <h3 style={{ margin: 0 }}>Change password</h3>
          <button type="button" className="btn btn-ghost btn-sm btn-icon" onClick={onClose}><X size={16} /></button>
        </div>
        <div className="form-group" style={{ marginBottom: 12 }}>
          <label>Current password</label>
          <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} required autoFocus />
        </div>
        <div className="form-group" style={{ marginBottom: 16 }}>
          <label>New password (min 8)</label>
          <input type="password" value={next} onChange={(e) => setNext(e.target.value)} required />
        </div>
        <button type="submit" className="btn btn-primary w-full" disabled={saving}>
          {saving ? <span className="spinner" style={{ width: 14, height: 14 }} /> : <KeyRound size={15} />} Update password
        </button>
      </form>
    </div>
  )
}

function DeleteAccountModal({ onClose, onDeleted }) {
  const [password, setPassword] = useState('')
  const [deleting, setDeleting] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setDeleting(true)
    try {
      await authApi.deleteAccount(password)
      onDeleted()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to delete account')
      setDeleting(false)
    }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 1100, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', backdropFilter: 'blur(4px)' }}
      onClick={(e) => e.target === e.currentTarget && onClose()}>
      <form className="card fade-in modal-card" style={{ '--modal-w': '400px', padding: 24 }} onSubmit={submit}>
        <div className="flex items-center justify-between" style={{ marginBottom: 12 }}>
          <h3 style={{ margin: 0, color: 'var(--c-error)' }}>Delete account</h3>
          <button type="button" className="btn btn-ghost btn-sm btn-icon" onClick={onClose}><X size={16} /></button>
        </div>
        <p className="text-sm" style={{ color: 'var(--c-text-muted)', marginBottom: 16 }}>
          This permanently removes your name and email and disables your login.
          Designs and estimates you created remain, attributed to an anonymized
          account. This cannot be undone.
        </p>
        <div className="form-group" style={{ marginBottom: 16 }}>
          <label>Confirm your password</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoFocus />
        </div>
        <button type="submit" className="btn btn-danger w-full" disabled={deleting}>
          {deleting ? <span className="spinner" style={{ width: 14, height: 14 }} /> : <UserX size={15} />} Delete my account
        </button>
      </form>
    </div>
  )
}

export default function TopNav() {
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [showPwd, setShowPwd] = useState(false)
  const [showDelete, setShowDelete] = useState(false)

  const handleDeleted = () => {
    logout()
    navigate('/login')
    toast.success('Your account has been deleted')
  }

  const isHome = pathname === '/'
  const isCustomers = pathname.startsWith('/customers') || pathname.startsWith('/estimates')
  const isDesigns = pathname.startsWith('/designs')
  const canManage = user?.role === 'admin' || user?.role === 'owner'

  const handleLogout = () => { logout(); navigate('/login') }

  return (
    <nav className="dashboard-nav">
      <div className="flex items-center gap-3">
        <div
          onClick={() => navigate('/')}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => e.key === 'Enter' && navigate('/')}
          style={{
            width: 32, height: 32, background: 'var(--c-brand)', cursor: 'pointer',
            borderRadius: 7, display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
        >
          <svg width="18" height="18" fill="none" viewBox="0 0 24 24" stroke="#fff" strokeWidth={2.5}>
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <path d="M3 9h18M9 21V9" />
          </svg>
        </div>
        <span style={{ fontWeight: 800, fontSize: '1.1rem', letterSpacing: '-0.02em' }}>SteelCAD</span>

        <div className="flex items-center gap-1" style={{ marginLeft: 12 }}>
          <button className={`btn btn-sm ${isHome ? 'btn-secondary' : 'btn-ghost'}`} onClick={() => navigate('/')}>
            <LayoutDashboard size={15} /> Dashboard
          </button>
          <button className={`btn btn-sm ${isCustomers ? 'btn-secondary' : 'btn-ghost'}`} onClick={() => navigate('/customers')}>
            <Users size={15} /> Customers
          </button>
          <button className={`btn btn-sm ${isDesigns ? 'btn-secondary' : 'btn-ghost'}`} onClick={() => navigate('/designs')}>
            <LayoutGrid size={15} /> Design Library
          </button>
        </div>
      </div>

      <div className="flex items-center gap-2">
        {canManage && (
          <>
            <button className="btn btn-ghost btn-sm" onClick={() => navigate('/rates')}>
              <Settings size={15} /> Rates
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => navigate('/users')}>
              <UserCog size={15} /> Users
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => navigate('/settings')}>
              <Building2 size={15} /> Company
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => navigate('/activity')}>
              <Activity size={15} /> Activity
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => navigate('/trash')}>
              <Trash2 size={15} /> Trash
            </button>
          </>
        )}
        <div style={{
          padding: '4px 10px', background: 'var(--c-surface-2)',
          border: '1px solid var(--c-border)', borderRadius: 'var(--radius)', fontSize: '0.875rem',
          display: 'flex', alignItems: 'center', gap: 6,
        }}>
          {user?.name}
          {user?.role && (
            <span
              className="badge"
              style={{
                fontSize: '0.7rem', padding: '1px 6px', borderRadius: 4,
                ...(ROLE_BADGE_STYLE[user.role] || {}),
              }}
            >
              {ROLE_LABELS[user.role] ?? user.role}
            </span>
          )}
        </div>
        <button className="btn btn-ghost btn-sm btn-icon" onClick={() => setShowPwd(true)} title="Change password" aria-label="Change password">
          <KeyRound size={16} />
        </button>
        <button className="btn btn-ghost btn-sm btn-icon" onClick={() => setShowDelete(true)} title="Delete account" aria-label="Delete account">
          <UserX size={16} />
        </button>
        <button className="btn btn-ghost btn-sm btn-icon" onClick={handleLogout} title="Logout" aria-label="Logout">
          <LogOut size={16} />
        </button>
      </div>
      {showPwd && <ChangePasswordModal onClose={() => setShowPwd(false)} />}
      {showDelete && <DeleteAccountModal onClose={() => setShowDelete(false)} onDeleted={handleDeleted} />}
    </nav>
  )
}
