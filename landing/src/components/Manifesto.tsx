// "The shift" — flat prose block on the cream canvas.
export default function Manifesto() {
  return (
    <section className="section manifesto" id="about">
      <div className="wrap">
        <div className="sec-label">
          <span className="br">## </span>the shift
        </div>
        <p className="reveal">
          For decades, software made <span className="hl">you</span> the operator — switching tabs,
          chasing threads, and trying to <span className="u">remember what mattered.</span>
        </p>
        <p className="reveal d1">
          <span className="hl">Cash inverts that.</span> She watches your markets, clears your inbox,
          defends your calendar, and answers people on your behalf when you are away.
        </p>
        <p className="reveal d2">
          She <span className="hl">remembers every decision,</span> learns your judgment, and gets{' '}
          <span className="hl">measurably sharper</span> every week.
        </p>
        <p className="reveal d3">
          The only thing left for you is the part that was always yours alone.{' '}
          <span className="u">Decide. Create. Live.</span>
        </p>
      </div>
    </section>
  )
}
