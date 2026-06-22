// Comparison table — the grid rows are built imperatively by lib/compareTable
// into #ctable.
export default function Compare() {
  return (
    <section className="compare" id="compare">
      <div className="wrap">
        <div className="c-head">
          <span className="eyebrow">Comparison</span>
          <h2>
            See <span className="it">how Cash compares</span>
          </h2>
          <p>One managed intelligence versus DIY kits, bare CLIs, and locked-in copilots.</p>
        </div>
        <div className="ctable" id="ctable" />
        <div className="c-note">
          Comparison reflects typical configurations. Open-source projects vary by setup.
        </div>
      </div>
    </section>
  )
}
