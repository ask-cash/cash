const WITHOUT = [
  'Twelve tabs open, none of them talking to each other',
  'Decisions made weeks ago, already forgotten',
  'Markets moving while your inbox piles up',
  'You, personally, copy-pasting between five tools',
  'Every assistant forgets you the moment you close it',
]

const WITH = [
  'One intelligence wired across every tool you use',
  'Persistent memory that never loses the thread',
  'Markets, inbox and calendar handled before 8am',
  'Work happens autonomously, with your approval',
  'It learns your judgment and gets sharper weekly',
]

const Cross = () => (
  <span className="ic">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6">
      <line x1="6" y1="6" x2="18" y2="18" />
      <line x1="18" y1="6" x2="6" y2="18" />
    </svg>
  </span>
)

const Check = () => (
  <span className="ic">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  </span>
)

// Before / after split — the case for collapsing twelve apps into one mind.
export default function Problem() {
  return (
    <section className="problem" id="problem">
      <div className="wrap">
        <div className="p-head reveal">
          <span className="eyebrow">The problem</span>
          <h2>
            Your life runs on <span className="it">twelve disconnected apps.</span>
          </h2>
          <p>
            Context is scattered, nothing talks to anything, and you are the integration layer
            holding it all together. Cash replaces the chaos with one mind.
          </p>
        </div>
        <div className="p-split">
          <div className="p-col before reveal">
            <span className="tag">Without Cash</span>
            {WITHOUT.map((t) => (
              <div className="p-item" key={t}>
                <Cross />
                {t}
              </div>
            ))}
          </div>
          <div className="p-arrow reveal d1" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
              <line x1="5" y1="12" x2="19" y2="12" />
              <polyline points="12 5 19 12 12 19" />
            </svg>
          </div>
          <div className="p-col after reveal d2">
            <span className="tag">With Cash</span>
            {WITH.map((t) => (
              <div className="p-item" key={t}>
                <Check />
                {t}
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
