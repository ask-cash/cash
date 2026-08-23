import heroArtDots from '../assets/hero-art-dots.svg?raw'
import { openWaitlist } from '../lib/waitlist'

// Hero: the dot-matrix cat that scatters under the cursor (lib/heroArt), the
// Telegram-style conversation that types itself out (lib/heroChat), and the
// oversized "cash" wordmark anchored to the bottom of the card.
//
// The ~900 dot circles are kept in a separate .svg and inlined at build time —
// each one carries its own drift/scatter custom properties, so they have to be
// real nodes in the document rather than a referenced image.
export default function Hero() {
  return (
    <section className="hero">
      <div className="hero-chat reveal in" id="heroChat">
        <div className="hc-body" id="heroChatBody" />
      </div>

      <svg
        className="hero-art"
        id="heroArt"
        viewBox="0 0 560 560"
        aria-hidden="true"
        dangerouslySetInnerHTML={{ __html: heroArtDots }}
      />

      <div className="hero-foot">
        {/* <div className="pill-badge reveal in">
          <span className="tag">BETA</span> Now onboarding founders &amp; operators
        </div> */}
        <h1 className="hero-word reveal in d1">cash</h1>
        <div className="hero-line reveal in d2">
          <p className="hero-tag">Everything else, handled.</p>
          <button type="button" className="btn btn-primary btn-lg" onClick={openWaitlist}>
            Get access <span className="arr">→</span>
          </button>
        </div>
      </div>
    </section>
  )
}
