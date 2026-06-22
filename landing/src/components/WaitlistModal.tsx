import CashMark from './CashMark'

// "Get access" flow shell. The per-question screens inside #tfStage are rendered
// imperatively by lib/waitlist, which also submits the answers to Supabase.
export default function WaitlistModal() {
  return (
    <div className="tf-overlay" id="tfOverlay" role="dialog" aria-modal="true" aria-label="Get access to Cash">
      <div className="tf-progress">
        <span id="tfBar" />
      </div>
      <div className="tf-brand">
        <span className="m">
          <CashMark />
        </span>{' '}
        Cash
      </div>
      <button className="tf-close" id="tfClose" aria-label="Close">
        ✕
      </button>
      <div className="tf-stage" id="tfStage" />
      <div className="tf-foot-nav">
        <button id="tfPrev" aria-label="Previous question">
          ↑
        </button>
        <button id="tfNext" aria-label="Next question">
          ↓
        </button>
      </div>
    </div>
  )
}
