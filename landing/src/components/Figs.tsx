// Stat block — three ASCII sparse-line tiles with Fig. captions, in the
// manpage spirit. Plots are abstract, not real data points.
interface Fig {
  plot: string
  k: string
  cap: string
}
const FIGS: Fig[] = [
  {
    plot: `   ·
  · ·__
 ·     ·__·
·           `,
    k: 'Before 8 AM',
    cap: 'Fig 1. Your market brief lands before the day starts',
  },
  {
    plot: `·__
   ·__
      ·__
         ·`,
    k: '15 minutes',
    cap: 'Fig 2. A pre-meeting brief ahead of every call',
  },
  {
    plot: `        ·
     ·_·
  ·_·
·_·      `,
    k: 'Every week',
    cap: 'Fig 3. She reviews her own work and gets sharper',
  },
]

export default function Figs() {
  return (
    <section className="section" id="metrics">
      <div className="wrap">
        <div className="sec-label">
          <span className="br">## </span>what that feels like
        </div>
        <div className="figs">
          {FIGS.map((f) => (
            <div className="fig reveal" key={f.k}>
              <pre className="fig-plot" aria-hidden="true">
                {f.plot}
              </pre>
              <div className="fig-k">{f.k}</div>
              <div className="fig-cap">{f.cap}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
