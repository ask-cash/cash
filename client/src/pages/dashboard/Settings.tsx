import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  ChevronLeftIcon,
  GearIcon,
  LogOutIcon,
  MonitorIcon,
  PlugIcon,
  ShieldIcon,
  SlidersIcon,
} from '../../components/icons'
import { useAuth } from '../../lib/auth'

type SettingsSection = 'general' | 'integrations' | 'permissions' | 'security'

const SETTINGS_NAV = [
  { id: 'general', label: 'General', icon: SlidersIcon },
  { id: 'integrations', label: 'Integrations', icon: PlugIcon },
  { id: 'permissions', label: 'Permissions & privacy', icon: ShieldIcon },
  { id: 'security', label: 'Security', icon: GearIcon },
] as const

export default function Settings() {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()
  const [section, setSection] = useState<SettingsSection>('general')
  const [signingOut, setSigningOut] = useState(false)
  const profile = user?.profile
  const name = [profile?.firstName, profile?.lastName].filter(Boolean).join(' ') || 'Not set'
  const initials = (
    (profile?.firstName?.[0] || user?.email?.[0] || 'C') +
    (profile?.lastName?.[0] || '')
  ).toUpperCase()

  async function handleSignOut() {
    setSigningOut(true)
    await signOut()
    navigate('/signin', { replace: true })
  }

  return (
    <div className="settings-page">
      <header className="settings-page__header">
        <button type="button" className="settings-back" aria-label="Go back" onClick={() => navigate(-1)}>
          <ChevronLeftIcon />
        </button>
        <h1>Settings</h1>
      </header>

      <div className="settings-layout">
        <aside className="settings-nav" aria-label="Settings sections">
          <nav>
            {SETTINGS_NAV.map(({ id, label, icon: Icon }) => (
              <button
                type="button"
                key={id}
                className={section === id ? 'active' : ''}
                aria-current={section === id ? 'page' : undefined}
                onClick={() => setSection(id)}
              >
                <Icon />
                <span>{label}</span>
              </button>
            ))}
          </nav>
          <button
            type="button"
            className="settings-logout"
            disabled={signingOut}
            onClick={() => void handleSignOut()}
          >
            {signingOut ? <span className="spinner spinner--button" aria-hidden="true" /> : <LogOutIcon />}
            <span>{signingOut ? 'Signing out…' : 'Log out'}</span>
          </button>
        </aside>

        <div className="settings-content">
          {section === 'general' && (
            <>
              <section className="settings-panel" aria-labelledby="settings-general-title">
                <h2 id="settings-general-title">General</h2>
                <dl className="settings-summary">
                  <div><dt>Account</dt><dd>{profile?.email || user?.email || 'Not set'}</dd></div>
                  <div><dt>Name</dt><dd>{name}</dd></div>
                  <div><dt>Status</dt><dd><span className="status-chip status-chip--success"><span className="status-chip__dot" />Active</span></dd></div>
                  <div><dt>Role</dt><dd>{profile?.role || 'Not set'}</dd></div>
                  <div><dt>Onboarding</dt><dd>{profile?.onboarded ? 'Complete' : 'In progress'}</dd></div>
                </dl>
              </section>

              <section className="settings-panel" aria-labelledby="settings-profile-title">
                <div className="settings-panel__heading">
                  <div>
                    <h2 id="settings-profile-title">Profile</h2>
                    <p>How Cash identifies you and adapts to your workflow.</p>
                  </div>
                  <span className="profile-avatar" aria-hidden="true">{initials}</span>
                </div>
                <div className="settings-field">
                  <span>Name</span>
                  <strong>{name}</strong>
                </div>
                <div className="settings-field">
                  <span>Email</span>
                  <strong>{profile?.email || user?.email || 'Not set'}</strong>
                </div>
                <div className="settings-field">
                  <span>Platforms</span>
                  <div className="platform-list">
                    {profile?.platforms?.length
                      ? profile.platforms.map((platform) => <span className="platform-tag" key={platform}>{platform}</span>)
                      : <span className="platform-tag">None yet</span>}
                  </div>
                </div>
              </section>

              <section className="settings-panel" aria-labelledby="settings-theme-title">
                <div className="settings-panel__heading">
                  <div>
                    <h2 id="settings-theme-title">Theme</h2>
                    <p>Cash currently follows its focused dark workspace theme.</p>
                  </div>
                </div>
                <div className="theme-control" aria-label="Theme">
                  <button type="button" className="active"><MonitorIcon />System</button>
                  <button type="button" disabled>Light</button>
                  <button type="button" disabled>Dark</button>
                </div>
              </section>
            </>
          )}

          {section === 'integrations' && (
            <section className="settings-panel" aria-labelledby="settings-integrations-title">
              <div className="settings-panel__heading settings-panel__heading--split">
                <div>
                  <h2 id="settings-integrations-title">Integrations</h2>
                  <p>Services Cash can use on your behalf.</p>
                </div>
                <Link className="btn btn-ghost btn-small" to="/app/integrations">Open library</Link>
              </div>
              <div className="connection-row">
                <span className="integr-logo"><img src="/assets/logos/google-calendar.png" alt="" /></span>
                <div>
                  <h3>Google Calendar</h3>
                  <p>Calendar context, conflicts, and daily briefs.</p>
                </div>
                <span className={`status-chip ${profile?.calendarConnected ? 'status-chip--success' : 'status-chip--neutral'}`}>
                  <span className="status-chip__dot" />
                  {profile?.calendarConnected ? 'Connected' : 'Not connected'}
                </span>
              </div>
            </section>
          )}

          {section === 'permissions' && (
            <section className="settings-panel" aria-labelledby="settings-permissions-title">
              <div className="settings-panel__heading">
                <div>
                  <h2 id="settings-permissions-title">Permissions & privacy</h2>
                  <p>Cash only uses the information required for the features you enable.</p>
                </div>
                <ShieldIcon />
              </div>
              <dl className="settings-summary">
                <div><dt>Calendar access</dt><dd>{profile?.calendarConnected ? 'Enabled' : 'Not enabled'}</dd></div>
                <div><dt>Profile memory</dt><dd>Enabled</dd></div>
                <div><dt>Connected platforms</dt><dd>{profile?.platforms?.length || 0}</dd></div>
              </dl>
            </section>
          )}

          {section === 'security' && (
            <section className="settings-panel" aria-labelledby="settings-security-title">
              <div className="settings-panel__heading">
                <div>
                  <h2 id="settings-security-title">Security</h2>
                  <p>Review the active account and end this session when needed.</p>
                </div>
                <GearIcon />
              </div>
              <dl className="settings-summary">
                <div><dt>Signed in as</dt><dd>{user?.email}</dd></div>
                <div><dt>Session</dt><dd><span className="status-chip status-chip--success"><span className="status-chip__dot" />Active</span></dd></div>
              </dl>
              <button
                type="button"
                className="btn btn-danger settings-security-signout"
                disabled={signingOut}
                onClick={() => void handleSignOut()}
              >
                {signingOut && <span className="spinner spinner--button" aria-hidden="true" />}
                Sign out of Cash
              </button>
            </section>
          )}
        </div>
      </div>
    </div>
  )
}
