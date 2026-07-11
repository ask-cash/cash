import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import CashMark from '../components/CashMark'
import RotatingWord from '../components/RotatingWord'
import GoogleButton from '../components/GoogleButton'
import { useAuth } from '../lib/auth'

// The blueprint's rotating "Meet your new ___" — in Cash's voice.
const ROLES = [
  'Chief of Staff',
  'Calendar Wrangler',
  'Inbox Cat',
  'Finance Ops',
  'Reminder Machine',
  'Late-night Fixer',
]

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
    <div className="signup force-dark">
      <div className="signup__left">
        <div className="signup__brand">
          <span className="mark"><CashMark /></span> Cash
        </div>

        <form className="signup__form" onSubmit={submit}>
          <h1 className="signup__title">
            Meet your new
            <RotatingWord words={ROLES} />
          </h1>
          <p className="signup__sub">
            The sharp little cat who runs your calendar, inbox, and life admin —
            and gets smarter every week. (Yes, she did NOT wake up at 4:30 AM for this.)
          </p>

          {err && <div className="signup__err">{err}</div>}

          <GoogleButton label="Sign up with Google" onClick={signInWithGoogle} className="signup__btn" />
          <div className="signup__divider">or</div>

          <div className="signup__row">
            <div className="signup__field">
              <label>First name</label>
              <input className="signup__input" value={f.firstName} onChange={set('firstName')} placeholder="Suhail" autoComplete="given-name" />
            </div>
            <div className="signup__field">
              <label>Last name</label>
              <input className="signup__input" value={f.lastName} onChange={set('lastName')} placeholder="Khan" autoComplete="family-name" />
            </div>
          </div>
          <div className="signup__field">
            <label>Email</label>
            <input className="signup__input" type="email" value={f.email} onChange={set('email')} placeholder="you@company.com" autoComplete="email" />
          </div>
          <div className="signup__field">
            <label>Password</label>
            <input className="signup__input" type="password" value={f.password} onChange={set('password')} placeholder="At least 6 characters" autoComplete="new-password" />
          </div>

          <button className="signup__btn signup__btn--primary" disabled={busy}>
            {busy ? 'Waking Cash up…' : 'Continue'}
          </button>

          <p className="signup__alt">
            Already have an account? <Link to="/signin">Sign in</Link>
          </p>
        </form>
      </div>

      <div className="signup__right">
        <div className="signup__scene">
          <span className="cat"><CashMark /></span>
          <p className="quip">“I run the boring stuff so you don't have to.”</p>
        </div>
      </div>
    </div>
  )
}
