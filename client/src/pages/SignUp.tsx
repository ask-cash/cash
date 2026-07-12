import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import CashMark from '../components/CashMark'
import GoogleButton from '../components/GoogleButton'
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
      <div className="auth-shell">
        <div className="auth-brand"><span className="mark"><CashMark /></span> Cash</div>
        <h1 className="serif">Meet your new Chief of Staff</h1>
        <p className="auth-sub">
          The sharp little cat who runs your calendar, inbox, and life admin — and gets
          smarter every week. (She did NOT wake up at 4:30 AM for this.)
        </p>

        {err && <div className="auth-err">{err}</div>}

        <GoogleButton label="Sign up with Google" onClick={signInWithGoogle} />
        <div className="divider">or</div>

        <form onSubmit={submit}>
          <div className="row-2">
            <div className="field">
              <label>First name</label>
              <input value={f.firstName} onChange={set('firstName')} placeholder="Suhail" autoComplete="given-name" />
            </div>
            <div className="field">
              <label>Last name</label>
              <input value={f.lastName} onChange={set('lastName')} placeholder="Khan" autoComplete="family-name" />
            </div>
          </div>
          <div className="field">
            <label>Email</label>
            <input type="email" value={f.email} onChange={set('email')} placeholder="you@company.com" autoComplete="email" />
          </div>
          <div className="field">
            <label>Password</label>
            <input type="password" value={f.password} onChange={set('password')} placeholder="At least 6 characters" autoComplete="new-password" />
          </div>
          <button className="btn btn-primary btn-block" disabled={busy}>
            {busy ? 'Waking Cash up…' : 'Create account'}
          </button>
        </form>

        <p className="auth-alt">Already have an account? <Link to="/signin">Sign in</Link></p>
      </div>
    </div>
  )
}
