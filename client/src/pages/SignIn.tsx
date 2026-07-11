import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import CashMark from '../components/CashMark'
import GoogleButton from '../components/GoogleButton'
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
    if (error) return setErr(error)
    navigate('/app')
  }

  function google() {
    // Full-page redirect into the backend Google OAuth flow.
    signInWithGoogle()
  }

  return (
    <div className="auth-wrap">
      <div className="auth-shell">
        <div className="auth-brand"><span className="mark"><CashMark /></span> Cash</div>
        <h1>Welcome back</h1>
        <p className="auth-sub">Sign in to pick up where you and Cash left off.</p>

        {err && <div className="auth-err">{err}</div>}

        <GoogleButton label="Continue with Google" onClick={google} />
        <div className="divider">or</div>

        <form onSubmit={submit}>
          <div className="field">
            <label>Email</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" autoComplete="email" />
          </div>
          <div className="field">
            <label>Password</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Your password" autoComplete="current-password" />
          </div>
          <button className="btn btn-primary btn-block" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <p className="auth-alt">New to Cash? <Link to="/signup">Create an account</Link></p>
      </div>
    </div>
  )
}
