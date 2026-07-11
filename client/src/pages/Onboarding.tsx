import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import CashMark from '../components/CashMark'
import { CheckIcon } from '../components/icons'
import { ONBOARDING } from '../data/questions'
import { logoSrc } from '../data/logos'
import { useAuth } from '../lib/auth'

export default function Onboarding() {
  const { user, updateProfile } = useAuth()
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [role, setRole] = useState<string | null>(null)
  const [platforms, setPlatforms] = useState<string[]>(user?.profile.platforms || [])

  const q = ONBOARDING[step]
  const isLast = step === ONBOARDING.length - 1
  const canNext = q.id === 'role' ? !!role : true // platforms are optional

  function togglePlatform(opt: string) {
    setPlatforms((s) => (s.includes(opt) ? s.filter((x) => x !== opt) : [...s, opt]))
  }

  async function next() {
    if (!canNext) return
    if (!isLast) return setStep((s) => s + 1)
    await updateProfile({ role: role || undefined, platforms, onboarded: true })
    navigate('/connect-calendar')
  }

  const pct = Math.round(((step + 1) / (ONBOARDING.length + 1)) * 100)

  return (
    <div className="auth-wrap">
      <div className="auth-shell wide">
        <div className="auth-brand"><span className="mark"><CashMark /></span> Cash</div>

        <div className="wl-prog">
          <div className="wl-track"><span style={{ width: `${pct}%` }} /></div>
          <div className="wl-plabel">Step <b>{step + 1}</b> of {ONBOARDING.length + 1}</div>
        </div>

        <h1 style={{ fontSize: 24 }}>{q.q}</h1>
        <p className="auth-sub">{q.sub}</p>

        <div className="pills">
          {q.options.map((opt) => {
            const on = q.id === 'role' ? role === opt : platforms.includes(opt)
            const logo = q.logos ? logoSrc(opt) : ''
            return (
              <button
                key={opt}
                type="button"
                className={'pill' + (on ? ' on' : '')}
                onClick={() => (q.id === 'role' ? setRole(opt) : togglePlatform(opt))}
              >
                {logo && <img src={logo} alt="" width={16} height={16} style={{ borderRadius: 4 }} />}
                {opt}
                <span className="ck"><CheckIcon /></span>
              </button>
            )
          })}
        </div>

        <div className="center-actions">
          {step > 0 && (
            <button className="btn btn-ghost" style={{ flex: '0 0 auto' }} onClick={() => setStep((s) => s - 1)}>
              Back
            </button>
          )}
          <button className="btn btn-primary" disabled={!canNext} onClick={next}>
            {isLast ? 'Continue' : 'Next'}
          </button>
        </div>
      </div>
    </div>
  )
}
