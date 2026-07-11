import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import CashMark from '../../components/CashMark'
import { ActivityIcon, ChatIcon, PlugIcon, GearIcon } from '../../components/icons'
import { useAuth } from '../../lib/auth'

// Primary nav (blueprint §7.1): Activity is the home surface; Chat, Integrations
// and Settings are siblings.
const NAV = [
  { to: '/app', label: 'Activity', icon: ActivityIcon, end: true },
  { to: '/app/chat', label: 'Chat', icon: ChatIcon, end: false },
  { to: '/app/integrations', label: 'Integrations', icon: PlugIcon, end: false },
  { to: '/app/settings', label: 'Settings', icon: GearIcon, end: false },
]

export default function DashboardLayout() {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()
  const initials =
    (user?.profile.firstName?.[0] || user?.email?.[0] || 'C').toUpperCase() +
    (user?.profile.lastName?.[0] || '').toUpperCase()

  async function handleSignOut() {
    await signOut()
    navigate('/signin', { replace: true })
  }

  return (
    <div className="app-shell">
      <aside className="app-side">
        <div className="auth-brand">
          <span className="mark"><CashMark /></span>
          Cash
        </div>
        <nav className="side-nav">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => 'side-link' + (isActive ? ' active' : '')}
            >
              <Icon />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="side-foot">
          <div className="side-user">
            <span className="side-avatar">{initials}</span>
            <span className="who">
              <b>{user?.profile.firstName || 'You'}</b>
              <span>{user?.email}</span>
            </span>
          </div>
          <button className="btn btn-ghost btn-block" style={{ marginTop: 10 }} onClick={handleSignOut}>
            Sign out
          </button>
        </div>
      </aside>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  )
}
