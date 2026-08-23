import type { ReactNode } from 'react'

interface Step {
  num: string
  icon: ReactNode
  title: string
  body: string
  chips: string[]
}

const STEPS: Step[] = [
  {
    num: 'STEP 01',
    icon: (
      <>
        <path d="M9 17H7A5 5 0 0 1 7 7h2" />
        <path d="M15 7h2a5 5 0 0 1 0 10h-2" />
        <line x1="8" y1="12" x2="16" y2="12" />
      </>
    ),
    title: 'Connect',
    body: 'Link your calendar, email, chat, code and market feeds through secure, revocable connections. Cash maps your world in minutes.',
    chips: ['Calendar', 'Gmail', 'Slack', 'GitHub', 'Markets'],
  },
  {
    num: 'STEP 02',
    icon: (
      <>
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
      </>
    ),
    title: 'Configure',
    body: 'Tell Cash your goals, risk profile, working hours and how you like to communicate. It adapts to your judgment, not a template.',
    chips: ['Goals', 'Risk profile', 'Focus rules', 'Tone'],
  },
  {
    num: 'STEP 03',
    icon: <polygon points="5 3 19 12 5 21 5 3" />,
    title: 'Run',
    body: 'Cash works autonomously (briefing, scheduling, replying, researching) and reviews its own performance every single week.',
    chips: ['Autonomous', 'Self-improving', 'Weekly review'],
  },
]

const DELAY = ['', 'd1', 'd2']

export default function HowItWorks() {
  return (
    <section className="howto" id="how">
      <div className="wrap">
        <div className="h-head reveal">
          <span className="eyebrow">How it works</span>
          <h2>
            Live in an afternoon. <span className="it">Compounding</span> from week one.
          </h2>
          <p>
            Connect your stack, set your preferences, and let Cash run. It reviews its own work every
            week to get measurably better.
          </p>
        </div>
        <div className="h-steps">
          {STEPS.map((s, i) => (
            <div className={`h-step reveal ${DELAY[i]}`.trim()} key={s.title}>
              <div className="num">{s.num}</div>
              <div className="ic">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
                  {s.icon}
                </svg>
              </div>
              <h3>{s.title}</h3>
              <p>{s.body}</p>
              <div className="chips">
                {s.chips.map((c) => (
                  <span key={c}>{c}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
