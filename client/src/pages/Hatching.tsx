import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import CashMark from '../components/CashMark'
import { useAuth } from '../lib/auth'

// The onboarding finale (blueprint §5.4, "hatching"): Cash waking up, then into
// the dashboard. Auto-advances; a couple of beats of personality.
const LINES = [
  'Waking Cash up…',
  'Stretching. Blinking. Judging your calendar.',
  "She's up. Barely.",
]

export default function Hatching() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [line, setLine] = useState(0)

  useEffect(() => {
    const beats = [
      setTimeout(() => setLine(1), 1100),
      setTimeout(() => setLine(2), 2300),
      setTimeout(() => navigate('/app', { replace: true }), 3400),
    ]
    return () => beats.forEach(clearTimeout)
  }, [navigate])

  return (
    <div className="hatch">
      <span className="hatch__glow" />
      <div>
        <div className="hatch__cat"><CashMark /></div>
        <h1 className="hatch__title serif">
          {line < 2 ? LINES[line] : `You're all set, ${user?.profile.firstName || 'friend'}.`}
        </h1>
        <p className="hatch__sub">{line < 2 ? 'Just a moment…' : "I did NOT wake up at 4:30 AM for this. Let's go. 🐾"}</p>
      </div>
    </div>
  )
}
