// Integrations marquee — the three scrolling rows are filled imperatively by
// lib/marquee.
export default function Marquee() {
  return (
    <section className="intmarq">
      <div className="imq-head">
        <span className="eyebrow">Integrations</span>
        <h2>
          Plugs into <span className="it">everything</span> you already run on.
        </h2>
        <p>One intelligence, wired across your whole stack — finance, comms, calendar, code, and more.</p>
      </div>
      <div className="imq-row rl" id="imqRow1" />
      <div className="imq-row lr" id="imqRow2" />
      <div className="imq-row rl" id="imqRow3" />
    </section>
  )
}
