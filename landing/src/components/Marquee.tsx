import { INTEGR } from '../data/integrations'

// Integrations marquee — the two rows scroll in opposite directions and are
// filled from the integration data by lib/marquee.
export default function Marquee() {
  return (
    <section className="intmarq" id="intmarq">
      <div className="imq-head">
        <span className="eyebrow">Integrations</span>
        <h2>
          Wired into <span className="it">everything</span> you already run on.
        </h2>
        <p>
          One thread in Telegram, reaching across your calendar, your inbox, your code and your
          markets.
        </p>
      </div>
      <div className="imq-row rl" id="imqRow1" />
      <div className="imq-row lr" id="imqRow2" />
      <div className="imq-foot">
        <span className="imq-count">{INTEGR.length} connected</span>
        <span className="imq-more">More every week</span>
      </div>
    </section>
  )
}
