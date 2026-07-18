import { useMemo, useState, type FormEvent } from 'react'
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
import {
  formatCurrentTimeInZone,
  getBrowserTimeZone,
  getSupportedTimeZones,
  isValidTimeZone,
} from '../../lib/timezone'

type SettingsSection = 'general' | 'integrations' | 'permissions' | 'security'

const SETTINGS_NAV = [
  { id: 'general', label: 'General', icon: SlidersIcon },
  { id: 'integrations', label: 'Integrations', icon: PlugIcon },
  { id: 'permissions', label: 'Permissions & privacy', icon: ShieldIcon },
  { id: 'security', label: 'Security', icon: GearIcon },
] as const

export default function Settings() {
  const { user, signOut, updateProfile } = useAuth()
  const navigate = useNavigate()
  const [section, setSection] = useState<SettingsSection>('general')
  const [signingOut, setSigningOut] = useState(false)
  const profile = user?.profile
  const [detectedTimezone] = useState(getBrowserTimeZone)
  const savedTimezone = profile?.timezone || detectedTimezone
  const [timezoneDraft, setTimezoneDraft] = useState(savedTimezone)
  const [timezoneError, setTimezoneError] = useState<string | null>(null)
  const [timezoneNotice, setTimezoneNotice] = useState<{ tone: 'success' | 'error'; message: string } | null>(null)
  const [savingTimezone, setSavingTimezone] = useState(false)
  const timezoneOptions = useMemo(
    () => getSupportedTimeZones(savedTimezone, detectedTimezone),
    [savedTimezone, detectedTimezone],
  )
  const timezonePreview = formatCurrentTimeInZone(timezoneDraft.trim())
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

  async function saveTimezone(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (savingTimezone) return

    const timezone = timezoneDraft.trim()
    setTimezoneNotice(null)
    if (!isValidTimeZone(timezone)) {
      setTimezoneError('Enter a valid IANA time zone, such as Asia/Kolkata.')
      requestAnimationFrame(() => document.getElementById('settings-timezone')?.focus())
      return
    }

    setTimezoneError(null)
    setSavingTimezone(true)
    const error = await updateProfile({ timezone })
    setSavingTimezone(false)
    if (error) {
      setTimezoneNotice({ tone: 'error', message: error })
      return
    }
    setTimezoneDraft(timezone)
    setTimezoneNotice({
      tone: 'success',
      message: 'Time zone saved. New reminders will use this local time.',
    })
  }

  function useDetectedTimezone() {
    setTimezoneDraft(detectedTimezone)
    setTimezoneError(null)
    setTimezoneNotice(null)
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
                  <div><dt>Time zone</dt><dd>{savedTimezone}</dd></div>
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
                <div className="settings-field settings-field--timezone">
                  <label htmlFor="settings-timezone">Time zone</label>
                  <form className="settings-timezone" onSubmit={(event) => void saveTimezone(event)} noValidate>
                    <div className={`field${timezoneError ? ' field--error' : ''}`}>
                      <div className="settings-timezone__controls">
                        <input
                          id="settings-timezone"
                          name="timezone"
                          type="text"
                          list="settings-timezone-options"
                          value={timezoneDraft}
                          placeholder="Area/City"
                          autoComplete="off"
                          spellCheck={false}
                          disabled={savingTimezone}
                          aria-invalid={!!timezoneError}
                          aria-describedby={timezoneError
                            ? 'settings-timezone-hint settings-timezone-error'
                            : 'settings-timezone-hint'}
                          onChange={(event) => {
                            setTimezoneDraft(event.target.value)
                            setTimezoneError(null)
                            setTimezoneNotice(null)
                          }}
                        />
                        <datalist id="settings-timezone-options">
                          {timezoneOptions.map((timezone) => <option value={timezone} key={timezone} />)}
                        </datalist>
                        <button
                          type="submit"
                          className="btn btn-primary btn-small"
                          disabled={
                            savingTimezone
                            || !timezoneDraft.trim()
                            || timezoneDraft.trim() === savedTimezone
                          }
                        >
                          {savingTimezone && <span className="spinner spinner--button" aria-hidden="true" />}
                          {savingTimezone ? 'Saving…' : 'Save'}
                        </button>
                      </div>
                      <p className="form-hint" id="settings-timezone-hint">
                        {timezonePreview ? `Local time: ${timezonePreview}. ` : ''}
                        Used for reminders and daily planning.
                        {timezoneDraft.trim() !== detectedTimezone && (
                          <>
                            {' '}
                            <button type="button" className="timezone-detect" onClick={useDetectedTimezone}>
                              Use browser setting ({detectedTimezone})
                            </button>
                          </>
                        )}
                      </p>
                      {timezoneError && <p className="field-error" id="settings-timezone-error">{timezoneError}</p>}
                      {timezoneNotice && (
                        <p
                          className={`settings-timezone__notice settings-timezone__notice--${timezoneNotice.tone}`}
                          role={timezoneNotice.tone === 'error' ? 'alert' : 'status'}
                        >
                          {timezoneNotice.message}
                        </p>
                      )}
                    </div>
                  </form>
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
