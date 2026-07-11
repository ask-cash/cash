import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import CashMark from '../components/CashMark'
import GoogleButton from '../components/GoogleButton'
import { useAuth } from '../lib/auth'

// Login = the blueprint's forced-dark LoginShell + LoginCard (§4.3), Cash-styled.
export default function SignIn() {
  const { signIn, signInWithGoogle } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setErr(null)
    setBusy(true)
    const error = await signIn(email, password)
    setBusy(false)
    if (error) return setErr('Something went wrong. Please try again.')
    navigate('/app')
  }

  return (
    <div className="force-dark">
      <div className="login-shell">
        <div className="login-bg">
          <span className="login-bg__glow" />
          <span className="login-bg__mark"><CashMark /></span>
          <span className="login-bg__scene"><CashMark /></span>
        </div>

        <div className="login-card">
          <div className="brand"><span className="mark"><CashMark /></span> Cash</div>
          <h1 className="login-heading text-title-large">Sign in to Cash</h1>

          {err && <div className="login-error">{err}</div>}

          <GoogleButton label="Continue with Google" onClick={signInWithGoogle} className="signup__btn" />
          <div className="signup__divider">or</div>

          <form onSubmit={submit}>
            <div className="signup__field">
              <label>Email</label>
              <input className="signup__input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" autoComplete="email" />
            </div>
            <div className="signup__field">
              <label>Password</label>
              <input className="signup__input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Your password" autoComplete="current-password" />
            </div>
            <button className="signup__btn signup__btn--primary" disabled={busy} style={{ marginTop: 6 }}>
              {busy ? 'Letting you in…' : 'Continue'}
            </button>
          </form>

          <p className="signup__alt">
            Don't have an account? <Link to="/signup">Sign up</Link>
          </p>
        </div>
      </div>
    </div>
  )
}
