import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Brand from '../components/Brand'
import { CheckIcon } from '../components/icons'
import { ONBOARDING } from '../data/questions'
import { logoSrc } from '../data/logos'
import { useAuth } from '../lib/auth'

export default function Onboarding() {
  const { user, updateProfile } = useAuth()
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [role, setRole] = useState<string | null>(user?.profile.role || null)
  const [platforms, setPlatforms] = useState<string[]>(user?.profile.platforms || [])
  const [busy, setBusy] = useState(false)

  const question = ONBOARDING[step]
  const isLast = step === ONBOARDING.length - 1
  const canNext = question.id === 'role' ? !!role : true
  const totalSteps = ONBOARDING.length + 1
  const progress = Math.round(((step + 1) / totalSteps) * 100)

  function togglePlatform(option: string) {
    setPlatforms((current) => (
      current.includes(option) ? current.filter((item) => item !== option) : [...current, option]
    ))
  }

  async function next() {
    if (!canNext || busy) return
    if (!isLast) {
      setStep((current) => current + 1)
      return
    }

    setBusy(true)
    await updateProfile({ role: role || undefined, platforms, onboarded: true })
    navigate('/connect-calendar')
  }

  return (
    <div className="auth-wrap">
      <main className="auth-shell auth-shell--wide" aria-labelledby="onboarding-title">
        <Brand className="auth-brand" />

        <div
          className="progress"
          role="progressbar"
          aria-label="Onboarding progress"
          aria-valuemin={1}
          aria-valuemax={totalSteps}
          aria-valuenow={step + 1}
        >
          <div className="progress__meta">
            <span>Personalise Cash</span>
            <span>Step {step + 1} of {totalSteps}</span>
          </div>
          <div className="progress__track"><span style={{ width: `${progress}%` }} /></div>
        </div>

        <div className="onboarding-step" key={question.id}>
          <p className="eyebrow">{question.type === 'single' ? 'About you' : 'Your workflow'}</p>
          <h1 id="onboarding-title">{question.q}</h1>
          <p className="auth-sub">{question.sub}</p>

          <fieldset className="option-fieldset" disabled={busy}>
            <legend className="sr-only">{question.q}</legend>
            <div className="pills">
              {question.options.map((option) => {
                const selected = question.id === 'role' ? role === option : platforms.includes(option)
                const logo = question.logos ? logoSrc(option) : ''
                return (
                  <button
                    key={option}
                    type="button"
                    className={`pill${selected ? ' pill--selected' : ''}`}
                    aria-pressed={selected}
                    onClick={() => (question.id === 'role' ? setRole(option) : togglePlatform(option))}
                  >
                    {logo && <img src={logo} alt="" className="pill__logo" />}
                    <span>{option}</span>
                    <span className="pill__check" aria-hidden="true"><CheckIcon /></span>
                  </button>
                )
              })}
            </div>
          </fieldset>
        </div>

        <div className="center-actions">
          {step > 0 && (
            <button
              type="button"
              className="btn btn-ghost btn-back"
              disabled={busy}
              onClick={() => setStep((current) => current - 1)}
            >
              Back
            </button>
          )}
          <button type="button" className="btn btn-primary" disabled={!canNext || busy} onClick={next}>
            {busy && <span className="spinner spinner--button" aria-hidden="true" />}
            {busy ? 'Saving…' : isLast ? 'Continue' : 'Next'}
          </button>
        </div>
      </main>
    </div>
  )
}
