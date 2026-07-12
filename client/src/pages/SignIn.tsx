import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import GoogleButton from '../components/GoogleButton'
import AppleButton from '../components/AppleButton'
import { useAuth } from '../lib/auth'

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
    <div className="auth-wrap">
      <div className="auth-col">
        <h1 className="auth-page-title">Sign in</h1>
        <div className="auth-shell">
          {err && <div className="auth-err">{err}</div>}

          <form onSubmit={submit}>
            <div className="field">
              <label>Email</label>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Your email address" autoComplete="email" />
            </div>
            <div className="field">
              <label>Password</label>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Your password" autoComplete="current-password" />
            </div>
            <button className="btn btn-primary btn-block" disabled={busy}>
              {busy ? 'Letting you in…' : 'Continue'}
            </button>
          </form>

          <div className="divider">OR</div>

          <div className="social-stack">
            <GoogleButton label="Continue with Google" onClick={signInWithGoogle} />
            <AppleButton onClick={() => setErr('Apple sign-in is coming soon — use Google or email for now. 🐾')} />
          </div>

          <p className="auth-alt">Don't have an account? <Link to="/signup">Sign up</Link></p>
        </div>
      </div>
    </div>
  )
}
