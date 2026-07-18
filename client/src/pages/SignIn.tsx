import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import AppleButton from '../components/AppleButton'
import Brand from '../components/Brand'
import GoogleButton from '../components/GoogleButton'
import { useAuth } from '../lib/auth'

interface SignInErrors {
  email?: string
  password?: string
}

export default function SignIn() {
  const { signIn, signInWithGoogle } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fieldErrors, setFieldErrors] = useState<SignInErrors>({})
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  function validate() {
    const nextErrors: SignInErrors = {}
    if (!email.trim()) {
      nextErrors.email = 'Enter your email address.'
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      nextErrors.email = 'Enter a valid email address.'
    }
    if (!password) nextErrors.password = 'Enter your password.'
    setFieldErrors(nextErrors)

    if (nextErrors.email) {
      requestAnimationFrame(() => document.getElementById('signin-email')?.focus())
      return false
    }
    if (nextErrors.password) {
      requestAnimationFrame(() => document.getElementById('signin-password')?.focus())
      return false
    }
    return true
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    if (!validate()) return

    setBusy(true)
    const signInError = await signIn(email.trim(), password)
    setBusy(false)
    if (signInError) {
      setError('We couldn’t sign you in with those details. Check them and try again.')
      return
    }
    navigate('/app')
  }

  return (
    <div className="auth-wrap">
      <main className="auth-col" aria-labelledby="signin-title">
        <Brand className="auth-brand auth-brand--center" />
        <div className="auth-heading">
          <p className="eyebrow">Welcome back</p>
          <h1 id="signin-title">Sign in to Cash</h1>
          <p>Pick up where you left off.</p>
        </div>

        <section className="auth-shell">
          {error && <div className="status-banner status-banner--error" role="alert">{error}</div>}

          <form onSubmit={submit} noValidate aria-busy={busy}>
            <div className={`field${fieldErrors.email ? ' field--error' : ''}`}>
              <label htmlFor="signin-email">Email</label>
              <input
                id="signin-email"
                name="email"
                type="email"
                inputMode="email"
                value={email}
                onChange={(event) => {
                  setEmail(event.target.value)
                  setFieldErrors((current) => ({ ...current, email: undefined }))
                  setError(null)
                }}
                placeholder="you@example.com"
                autoComplete="email"
                required
                autoFocus
                aria-invalid={!!fieldErrors.email}
                aria-describedby={fieldErrors.email ? 'signin-email-error' : undefined}
              />
              {fieldErrors.email && <p className="field-error" id="signin-email-error">{fieldErrors.email}</p>}
            </div>

            <div className={`field${fieldErrors.password ? ' field--error' : ''}`}>
              <label htmlFor="signin-password">Password</label>
              <input
                id="signin-password"
                name="password"
                type="password"
                value={password}
                onChange={(event) => {
                  setPassword(event.target.value)
                  setFieldErrors((current) => ({ ...current, password: undefined }))
                  setError(null)
                }}
                placeholder="Your password"
                autoComplete="current-password"
                required
                aria-invalid={!!fieldErrors.password}
                aria-describedby={fieldErrors.password ? 'signin-password-error' : undefined}
              />
              {fieldErrors.password && <p className="field-error" id="signin-password-error">{fieldErrors.password}</p>}
            </div>

            <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
              {busy && <span className="spinner spinner--button" aria-hidden="true" />}
              {busy ? 'Signing in…' : 'Continue'}
            </button>
          </form>

          <div className="divider"><span>or continue with</span></div>

          <div className="social-stack">
            <GoogleButton label="Continue with Google" onClick={signInWithGoogle} disabled={busy} />
            <AppleButton
              disabled={busy}
              onClick={() => setError('Apple sign-in is coming soon. Use Google or email for now.')}
            />
          </div>

          <p className="auth-alt">New to Cash? <Link to="/signup">Create an account</Link></p>
        </section>
      </main>
    </div>
  )
}
