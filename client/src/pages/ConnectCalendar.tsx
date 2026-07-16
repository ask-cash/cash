import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Brand from '../components/Brand'
import { CheckIcon } from '../components/icons'

export default function ConnectCalendar() {
  const navigate = useNavigate()
  const [connecting, setConnecting] = useState(false)

  function connect() {
    setConnecting(true)
    window.location.href = '/api/connect/google/start'
  }

  return (
    <div className="auth-wrap">
      <main className="auth-shell calendar-connect" aria-labelledby="calendar-title">
        <Brand className="auth-brand" />

        <div className="connect-logo">
          <img src="/assets/logos/google-calendar.png" alt="" />
        </div>
        <p className="eyebrow">Final setup step</p>
        <h1 id="calendar-title">Connect Google Calendar</h1>
        <p className="auth-sub">
          Give Cash the context to brief your day, spot conflicts, and protect focus time.
        </p>

        <ul className="benefit-list">
          <li><CheckIcon /> Read your upcoming schedule</li>
          <li><CheckIcon /> Flag conflicts before they become a problem</li>
          <li><CheckIcon /> Prepare a useful morning brief</li>
        </ul>

        <button type="button" className="btn btn-primary btn-block" onClick={connect} disabled={connecting}>
          {connecting && <span className="spinner spinner--button" aria-hidden="true" />}
          {connecting ? 'Connecting…' : 'Connect Google Calendar'}
        </button>
        <p className="connection-note">You stay in control and can disconnect at any time.</p>
        <button
          type="button"
          className="text-button auth-skip"
          disabled={connecting}
          onClick={() => navigate('/hatching', { replace: true })}
        >
          Skip for now
        </button>
      </main>
    </div>
  )
}
