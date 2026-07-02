import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Plus, Trash2, X, KeyRound } from 'lucide-react'
import toast from 'react-hot-toast'
import { usersApi } from '../api/client'
import useAuthStore from '../store/authStore'
import { useConfirm } from '../components/ConfirmModal'

const ROLE_LABELS = { admin: 'Admin', owner: 'Owner', sales: 'Sales' }
const ROLE_COLORS = {
  admin: { background: 'var(--c-brand)', color: '#fff' },
  owner: { background: 'var(--c-success)', color: '#fff' },
  sales: { background: 'var(--c-surface-3)', color: 'var(--c-text-muted)' },
}

function InviteModal({ currentUserRole, onClose, onCreated }) {
  const [form, setForm] = useState({ name: '', email: '', password: '', role: 'sales' })
  const [saving, setSaving] = useState(false)

  const availableRoles = currentUserRole === 'admin'
    ? ['admin', 'owner', 'sales']
    : ['sales']

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.name.trim() || !form.email.trim() || !form.password.trim()) {
      toast.error('All fields are required')
      return
    }
    if (form.password.length < 8) {
      toast.error('Password must be at least 8 characters')
      return
    }
    setSaving(true)
    try {
      const { data } = await usersApi.create(form)
      toast.success(`${data.name} invited successfully`)
      onCreated(data)
      onClose()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to invite user')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
        backdropFilter: 'blur(4px)',
      }}
      onClick={onClose}
    >
      <div
        className="card modal-card"
        style={{ '--modal-w': '420px', padding: 24 }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center" style={{ justifyContent: 'space-between', marginBottom: 20 }}>
          <h3 style={{ margin: 0 }}>Invite User</h3>
          <button className="btn btn-ghost btn-sm btn-icon" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <label className="form-label">Full Name</label>
            <input
              className="input"
              placeholder="Jane Smith"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              autoFocus
            />
          </div>
          <div>
            <label className="form-label">Email</label>
            <input
              className="input"
              type="email"
              placeholder="jane@company.com"
              value={form.email}
              onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
            />
          </div>
          <div>
            <label className="form-label">Temporary Password</label>
            <input
              className="input"
              type="password"
              placeholder="Min. 8 characters"
              value={form.password}
              onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
            />
          </div>
          <div>
            <label className="form-label">Role</label>
            <select
              className="input"
              value={form.role}
              onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))}
            >
              {availableRoles.map((r) => (
                <option key={r} value={r}>{ROLE_LABELS[r]}</option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-2" style={{ justifyContent: 'flex-end', marginTop: 4 }}>
            <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? <span className="spinner" style={{ width: 14, height: 14 }} /> : <Plus size={15} />}
              Invite
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function ResetPasswordModal({ user, onClose }) {
  const [pwd, setPwd] = useState('')
  const [saving, setSaving] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    if (pwd.length < 8) { toast.error('Password must be at least 8 characters'); return }
    setSaving(true)
    try {
      await usersApi.resetPassword(user.id, pwd)
      toast.success(`Password reset for ${user.name}`)
      onClose()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to reset password')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1100, backdropFilter: 'blur(4px)' }}
      onClick={(e) => e.target === e.currentTarget && onClose()}>
      <form className="card modal-card" style={{ '--modal-w': '380px', padding: 24 }} onSubmit={submit}>
        <div className="flex items-center" style={{ justifyContent: 'space-between', marginBottom: 16 }}>
          <h3 style={{ margin: 0 }}>Reset password — {user.name}</h3>
          <button type="button" className="btn btn-ghost btn-sm btn-icon" onClick={onClose}><X size={16} /></button>
        </div>
        <div className="form-group" style={{ marginBottom: 16 }}>
          <label className="form-label">New temporary password (min 8)</label>
          <input className="input" type="text" value={pwd} onChange={(e) => setPwd(e.target.value)} autoFocus required />
        </div>
        <button type="submit" className="btn btn-primary w-full" disabled={saving}>
          {saving ? <span className="spinner" style={{ width: 14, height: 14 }} /> : <KeyRound size={15} />} Set password
        </button>
      </form>
    </div>
  )
}

export default function UsersPage() {
  const navigate = useNavigate()
  const currentUser = useAuthStore((s) => s.user)
  const [resetTarget, setResetTarget] = useState(null)
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [showInvite, setShowInvite] = useState(false)
  const { confirm, ConfirmDialog } = useConfirm()
  const [updatingRole, setUpdatingRole] = useState(null)
  const [deletingId, setDeletingId] = useState(null)

  const isAdmin = currentUser?.role === 'admin'
  const availableRoles = isAdmin ? ['admin', 'owner', 'sales'] : ['sales']

  useEffect(() => {
    usersApi.list()
      .then(({ data }) => setUsers(data))
      .catch(() => toast.error('Failed to load users'))
      .finally(() => setLoading(false))
  }, [])

  const handleRoleChange = async (userId, newRole) => {
    setUpdatingRole(userId)
    try {
      const { data } = await usersApi.updateRole(userId, newRole)
      setUsers((prev) => prev.map((u) => u.id === userId ? data : u))
      toast.success('Role updated')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to update role')
    } finally {
      setUpdatingRole(null)
    }
  }

  const handleDelete = async (user) => {
    if (!await confirm(`Delete ${user.name}? This cannot be undone.`, { title: 'Delete User', confirmLabel: 'Delete' })) return
    setDeletingId(user.id)
    try {
      await usersApi.delete(user.id)
      setUsers((prev) => prev.filter((u) => u.id !== user.id))
      toast.success('User deleted')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to delete user')
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div className="dashboard-layout">
      <nav className="dashboard-nav">
        <div className="flex items-center gap-3">
          <button className="btn btn-ghost btn-sm btn-icon" onClick={() => navigate('/')} aria-label="Back">
            <ArrowLeft size={17} />
          </button>
          <h3 style={{ margin: 0 }}>User Management</h3>
        </div>
        <button className="btn btn-primary btn-sm" onClick={() => setShowInvite(true)}>
          <Plus size={15} /> Invite User
        </button>
      </nav>

      <main className="dashboard-main fade-in">
        <div style={{ marginBottom: 24 }}>
          <h1 style={{ marginBottom: 8 }}>Users</h1>
          <p style={{ color: 'var(--c-text-muted)' }}>
            Manage who has access to SteelCAD. New users must be invited — there is no public sign-up.
          </p>
        </div>

        {loading ? (
          <div className="flex items-center justify-center" style={{ height: 300 }}>
            <div className="spinner" style={{ width: 32, height: 32 }} />
          </div>
        ) : (
          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  {['Name', 'Email', 'Role', 'Joined', ''].map((h) => (
                    <th key={h} style={{
                      textAlign: 'left', padding: '10px 16px',
                      fontSize: '0.75rem', fontWeight: 600,
                      color: 'var(--c-text-muted)', textTransform: 'uppercase',
                      borderBottom: '1px solid var(--c-border)',
                      background: 'var(--c-surface-2)',
                    }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {users.length === 0 ? (
                  <tr>
                    <td colSpan={5} style={{ padding: 32, textAlign: 'center', color: 'var(--c-text-muted)' }}>
                      No users yet. Invite someone to get started.
                    </td>
                  </tr>
                ) : users.map((u) => {
                  const isSelf = u.id === currentUser?.id
                  return (
                    <tr key={u.id} style={{ borderBottom: '1px solid var(--c-border)' }}>
                      <td style={{ padding: '12px 16px', fontWeight: 500 }}>
                        {u.name}
                        {isSelf && (
                          <span style={{ marginLeft: 6, fontSize: '0.75rem', color: 'var(--c-text-muted)' }}>
                            (you)
                          </span>
                        )}
                      </td>
                      <td style={{ padding: '12px 16px', color: 'var(--c-text-muted)', fontSize: '0.875rem' }}>
                        {u.email}
                      </td>
                      <td style={{ padding: '8px 16px' }}>
                        {isSelf ? (
                          <span
                            className="badge"
                            style={{ fontSize: '0.75rem', padding: '2px 8px', borderRadius: 4, ...(ROLE_COLORS[u.role] || {}) }}
                          >
                            {ROLE_LABELS[u.role] ?? u.role}
                          </span>
                        ) : (
                          <select
                            className="input"
                            style={{ padding: '3px 8px', fontSize: '0.8rem', width: 'auto' }}
                            value={u.role}
                            disabled={updatingRole === u.id}
                            onChange={(e) => handleRoleChange(u.id, e.target.value)}
                          >
                            {availableRoles.map((r) => (
                              <option key={r} value={r}>{ROLE_LABELS[r]}</option>
                            ))}
                          </select>
                        )}
                      </td>
                      <td style={{ padding: '12px 16px', color: 'var(--c-text-muted)', fontSize: '0.8rem' }}>
                        {new Date(u.created_at).toLocaleDateString()}
                      </td>
                      <td style={{ padding: '8px 16px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                        {!isSelf && (isAdmin || u.role === 'sales') && (
                          <button
                            className="btn btn-ghost btn-sm btn-icon"
                            onClick={() => setResetTarget(u)}
                            title="Reset password"
                            aria-label={`Reset password for ${u.name}`}
                          >
                            <KeyRound size={14} />
                          </button>
                        )}
                        {isAdmin && !isSelf && (
                          <button
                            className="btn btn-ghost btn-sm btn-icon"
                            onClick={() => handleDelete(u)}
                            disabled={deletingId === u.id}
                            title="Delete user"
                            aria-label={`Delete ${u.name}`}
                          >
                            {deletingId === u.id
                              ? <span className="spinner" style={{ width: 13, height: 13 }} />
                              : <Trash2 size={14} />}
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </main>

      {showInvite && (
        <InviteModal
          currentUserRole={currentUser?.role}
          onClose={() => setShowInvite(false)}
          onCreated={(user) => setUsers((prev) => [...prev, user])}
        />
      )}
      {resetTarget && <ResetPasswordModal user={resetTarget} onClose={() => setResetTarget(null)} />}
      {ConfirmDialog}
    </div>
  )
}
