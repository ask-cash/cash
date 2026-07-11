import { useNavigate } from 'react-router-dom'
import CashMark from '../components/CashMark'

// Final onboarding step: connect Google Calendar via the backend's real OAuth
// flow (the callback stores the token in the per-tenant vault), or skip to the
// dashboard. Onboarding already marked the profile onboarded before this step.
export default function ConnectCalendar() {
  const navigate = useNavigate()

  function connect() {
    window.location.href = '/api/connect/google/start'
  }

  return (
    <div className="auth-wrap">
      <div className="auth-shell">
        <div className="auth-brand"><span className="mark"><CashMark /></span> Cash</div>

        <div className="integr-logo" style={{ width: 56, height: 56, marginBottom: 18 }}>
          <img src="/assets/logos/google-calendar.png" alt="Google Calendar" style={{ width: 34, height: 34 }} />
        </div>
        <h1>Connect Google Calendar</h1>
        <p className="auth-sub">
          This is the big one. With your calendar, Cash can see your day, flag conflicts, protect
          your focus time, and send you a morning brief. You can connect more later.
        </p>

        <button className="btn btn-primary btn-block" onClick={connect}>
          Connect Google Calendar
        </button>
        <p className="auth-alt">
          <a onClick={() => navigate('/app', { replace: true })} style={{ cursor: 'pointer' }}>Skip for now</a>
        </p>
      </div>
    </div>
  )
}
