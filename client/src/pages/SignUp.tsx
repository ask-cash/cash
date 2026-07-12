import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import GoogleButton from '../components/GoogleButton'
import AppleButton from '../components/AppleButton'
import { useAuth } from '../lib/auth'

export default function SignUp() {
  const { signUp, signInWithGoogle } = useAuth()
  const navigate = useNavigate()
  const [f, setF] = useState({ firstName: '', lastName: '', email: '', password: '' })
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setF((s) => ({ ...s, [k]: e.target.value }))

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setErr(null)
    if (!f.firstName || !f.email || f.password.length < 6) {
      setErr('Give me your name, email, and a password of at least 6 characters. 🐾')
      return
    }
    setBusy(true)
    const error = await signUp(f)
    setBusy(false)
    if (error) return setErr(error)
    navigate('/onboarding')
  }

  return (
    <div className="auth-wrap">
      <div className="auth-col">
        <h1 className="auth-page-title">Sign up</h1>
        <div className="auth-shell">
          {err && <div className="auth-err">{err}</div>}

          <form onSubmit={submit}>
            <div className="row-2">
              <div className="field">
                <label>First name</label>
                <input value={f.firstName} onChange={set('firstName')} placeholder="Your first name" autoComplete="given-name" />
              </div>
              <div className="field">
                <label>Surname</label>
                <input value={f.lastName} onChange={set('lastName')} placeholder="Your surname" autoComplete="family-name" />
              </div>
            </div>
            <div className="field">
              <label>Email</label>
              <input type="email" value={f.email} onChange={set('email')} placeholder="Your email address" autoComplete="email" />
            </div>
            <div className="field">
              <label>Password</label>
              <input type="password" value={f.password} onChange={set('password')} placeholder="At least 6 characters" autoComplete="new-password" />
            </div>
            <button className="btn btn-primary btn-block" disabled={busy}>
              {busy ? 'Waking Cash up…' : 'Continue'}
            </button>
          </form>

          <div className="divider">OR</div>

          <div className="social-stack">
            <GoogleButton label="Continue with Google" onClick={signInWithGoogle} />
            <AppleButton onClick={() => setErr('Apple sign-in is coming soon — use Google or email for now. 🐾')} />
          </div>

          <p className="auth-alt">Already have an account? <Link to="/signin">Sign in</Link></p>
        </div>
      </div>
    </div>
  )
}
