import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import AppleButton from '../components/AppleButton'
import Brand from '../components/Brand'
import GoogleButton from '../components/GoogleButton'
import { useAuth } from '../lib/auth'
import { getBrowserTimeZone } from '../lib/timezone'

interface SignUpForm {
  firstName: string
  lastName: string
  email: string
  password: string
}

type FieldErrors = Partial<Record<keyof SignUpForm, string>>

export default function SignUp() {
  const { signUp, signInWithGoogle } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState<SignUpForm>({ firstName: '', lastName: '', email: '', password: '' })
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  function set(key: keyof SignUpForm) {
    return (event: React.ChangeEvent<HTMLInputElement>) => {
      setForm((current) => ({ ...current, [key]: event.target.value }))
      setFieldErrors((current) => ({ ...current, [key]: undefined }))
      setError(null)
    }
  }

  function validate() {
    const nextErrors: FieldErrors = {}
    if (!form.firstName.trim()) nextErrors.firstName = 'Enter your first name.'
    if (!form.email.trim()) {
      nextErrors.email = 'Enter your email address.'
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) {
      nextErrors.email = 'Enter a valid email address.'
    }
    if (form.password.length < 6) nextErrors.password = 'Use at least 6 characters.'

    setFieldErrors(nextErrors)
    const firstInvalid = (['firstName', 'email', 'password'] as const).find((key) => nextErrors[key])
    if (firstInvalid) {
      requestAnimationFrame(() => document.getElementById(`signup-${firstInvalid}`)?.focus())
      return false
    }
    return true
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    if (!validate()) return

    setBusy(true)
    const signUpError = await signUp({
      ...form,
      firstName: form.firstName.trim(),
      lastName: form.lastName.trim(),
      email: form.email.trim(),
      timezone: getBrowserTimeZone(),
    })
    setBusy(false)
    if (signUpError) {
      setError(signUpError)
      return
    }
    navigate('/onboarding')
  }

  return (
    <div className="auth-wrap">
      <main className="auth-col" aria-labelledby="signup-title">
        <Brand className="auth-brand auth-brand--center" />
        <div className="auth-heading">
          <p className="eyebrow">Get started</p>
          <h1 id="signup-title">Create your account</h1>
          <p>Set up Cash in a couple of minutes. You can connect your tools after this.</p>
        </div>

        <section className="auth-shell">
          {error && <div className="status-banner status-banner--error" role="alert">{error}</div>}

          <form onSubmit={submit} noValidate aria-busy={busy}>
            <div className="row-2">
              <div className={`field${fieldErrors.firstName ? ' field--error' : ''}`}>
                <label htmlFor="signup-firstName">First name</label>
                <input
                  id="signup-firstName"
                  name="firstName"
                  value={form.firstName}
                  onChange={set('firstName')}
                  placeholder="Your first name"
                  autoComplete="given-name"
                  required
                  aria-invalid={!!fieldErrors.firstName}
                  aria-describedby={fieldErrors.firstName ? 'signup-firstName-error' : undefined}
                />
                {fieldErrors.firstName && <p className="field-error" id="signup-firstName-error">{fieldErrors.firstName}</p>}
              </div>
              <div className="field">
                <label htmlFor="signup-lastName">Surname <span className="label-optional">Optional</span></label>
                <input
                  id="signup-lastName"
                  name="lastName"
                  value={form.lastName}
                  onChange={set('lastName')}
                  placeholder="Your surname"
                  autoComplete="family-name"
                />
              </div>
            </div>

            <div className={`field${fieldErrors.email ? ' field--error' : ''}`}>
              <label htmlFor="signup-email">Email</label>
              <input
                id="signup-email"
                name="email"
                type="email"
                inputMode="email"
                value={form.email}
                onChange={set('email')}
                placeholder="you@example.com"
                autoComplete="email"
                required
                aria-invalid={!!fieldErrors.email}
                aria-describedby={fieldErrors.email ? 'signup-email-error' : undefined}
              />
              {fieldErrors.email && <p className="field-error" id="signup-email-error">{fieldErrors.email}</p>}
            </div>

            <div className={`field${fieldErrors.password ? ' field--error' : ''}`}>
              <label htmlFor="signup-password">Password</label>
              <input
                id="signup-password"
                name="password"
                type="password"
                value={form.password}
                onChange={set('password')}
                placeholder="At least 6 characters"
                autoComplete="new-password"
                minLength={6}
                required
                aria-invalid={!!fieldErrors.password}
                aria-describedby={fieldErrors.password ? 'signup-password-hint signup-password-error' : 'signup-password-hint'}
              />
              <p className="form-hint" id="signup-password-hint">Use 6 or more characters.</p>
              {fieldErrors.password && <p className="field-error" id="signup-password-error">{fieldErrors.password}</p>}
            </div>

            <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
              {busy && <span className="spinner spinner--button" aria-hidden="true" />}
              {busy ? 'Creating account…' : 'Continue'}
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

          <p className="auth-alt">Already have an account? <Link to="/signin">Sign in</Link></p>
        </section>
      </main>
    </div>
  )
}
