import { useAuth } from '../../lib/auth'

export default function Settings() {
  const { user } = useAuth()
  const p = user?.profile

  return (
    <>
      <div className="app-head"><h1>Settings</h1></div>
      <div className="app-body">
        <div className="set-card">
          <h3>Profile</h3>
          <p className="section-note">How Cash knows you.</p>
          <div className="set-row"><span className="k">Name</span><span className="v">{[p?.firstName, p?.lastName].filter(Boolean).join(' ') || '—'}</span></div>
          <div className="set-row"><span className="k">Email</span><span className="v">{p?.email || '—'}</span></div>
          <div className="set-row"><span className="k">Role</span><span className="v">{p?.role || 'Not set'}</span></div>
          <div className="set-row"><span className="k">Platforms</span><span className="v">{p?.platforms?.length ? p.platforms.join(', ') : 'None yet'}</span></div>
        </div>

        <div className="set-card">
          <h3>Connections</h3>
          <div className="set-row">
            <span className="k">Google Calendar</span>
            <span className="v">{p?.calendarConnected ? 'Connected' : 'Not connected'}</span>
          </div>
        </div>

      </div>
    </>
  )
}
