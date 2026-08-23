import { FEATURES } from '../data/features'

// Feature rows with ASCII bracket bullets — the brand's only iconography.
export default function FeatureList() {
  return (
    <section className="section" id="features">
      <div className="wrap">
        <div className="sec-label">
          <span className="br">## </span>what she runs for you
        </div>
        <div className="list">
          {FEATURES.map((f) => (
            <div className="list-row reveal" key={f.label}>
              <span className="lr-mark">{f.mark}</span>
              <span className="lr-label">{f.label}</span>
              <span className="lr-desc">{f.desc}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
