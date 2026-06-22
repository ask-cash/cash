export default function Ethos() {
  return (
    <section className="section ethos" id="ethos">
      <div className="ethos-spot" id="ethosSpot" aria-hidden="true" />
      <div className="wrap">
        <div className="eyebrow">The shift</div>
        <div className="ethos-sentences" id="ethosBlock">
          <p className="ethos-sent reveal">
            For decades, software made you the operator — switching tabs, chasing threads, and trying
            to <span className="hl-u">remember what mattered.</span>
          </p>
          <p className="ethos-sent reveal d1">
            <span className="hl">Cash inverts that.</span> It watches your markets, clears your inbox,
            defends your calendar, runs your research, and ships your code.
          </p>
          <p className="ethos-sent reveal d2">
            It <span className="hl">remembers every decision,</span> learns your judgment, and gets{' '}
            <span className="hl">measurably sharper</span> every week.
          </p>
          <p className="ethos-sent reveal d3">
            The only thing left for you is the part that was always yours alone.{' '}
            <span className="hl-u">Decide. Create. Live.</span>
          </p>
        </div>
        <div className="ethos-foot">
          <div className="ethos-stat reveal d1">
            <div className="k">Before 8 AM</div>
            <div className="v">Your market brief lands before the day starts</div>
          </div>
          <div className="ethos-stat reveal d2">
            <div className="k">15 minutes</div>
            <div className="v">Pre-meeting brief ahead of every call</div>
          </div>
          <div className="ethos-stat reveal d3">
            <div className="k">Every week</div>
            <div className="v">It reviews its own work and improves</div>
          </div>
        </div>
      </div>
    </section>
  )
}
