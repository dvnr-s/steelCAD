/**
 * Shared top navigation bar.
 */
import { useNavigate, useLocation } from 'react-router-dom'
import { LogOut, Settings, Users, LayoutGrid, UserCog } from 'lucide-react'
import useAuthStore from '../store/authStore'

const ROLE_LABELS = { admin: 'Admin', owner: 'Owner', sales: 'Sales' }
const ROLE_BADGE_STYLE = {
  admin: { background: 'var(--c-brand)', color: '#fff' },
  owner: { background: 'var(--c-success)', color: '#fff' },
  sales: { background: 'var(--c-surface-3)', color: 'var(--c-text-muted)' },
}

export default function TopNav() {
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const navigate = useNavigate()
  const { pathname } = useLocation()

  const isCustomers = pathname === '/' || pathname.startsWith('/customers') || pathname.startsWith('/estimates')
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
          <button className={`btn btn-sm ${isCustomers ? 'btn-secondary' : 'btn-ghost'}`} onClick={() => navigate('/')}>
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
        <button className="btn btn-ghost btn-sm btn-icon" onClick={handleLogout} title="Logout" aria-label="Logout">
          <LogOut size={16} />
        </button>
      </div>
    </nav>
  )
}
