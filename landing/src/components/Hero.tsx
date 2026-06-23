import CashMark from './CashMark'

// Static hero skeleton. The orbiting integration logos, scene connector lines,
// action toasts and the phone chat loop are populated imperatively by
// lib/heroScene once mounted.
export default function Hero() {
  return (
    <section className="hero">
      <div className="hero-bg" aria-hidden="true">
        <div className="orb a" />
        <div className="orb b" />
        <div className="orb c" />
        <div className="grid" />
      </div>
      <div className="wrap">
        <div className="hero-top">
          {/* <div className="pill-badge reveal in">
            <span className="tag">BETA</span> Now onboarding founders &amp; operators
          </div> */}
          <h1 className="reveal in d1">
            One intelligence to run
            <br />
            <span className="grad-blue">your entire life.</span>
          </h1>
          <p className="sub reveal in d2">
            Cash is your personal AI operating system — managing your finances, calendar, inbox,
            research, and code autonomously. It works while you live, and gets sharper every week.
          </p>
          <div className="hero-cta reveal in d3">
            <a href="#waitlist" className="btn btn-primary btn-lg">
              Get access <span className="arr">→</span>
            </a>
          </div>
          <div className="hero-logos reveal" id="heroLogos" />
          <div className="hero-meta reveal in d4">
          </div>
        </div>

        {/* product preview: phone + orbiting integrations */}
        <div className="hero-scene" id="heroScene">
          <div className="scene-glow" aria-hidden="true" />
          <svg className="scene-lines" id="sceneLines" aria-hidden="true" preserveAspectRatio="xMidYMid meet" />
          <div className="orbit-field" id="orbitField" aria-hidden="true" />
          <div className="toast-layer" id="toastLayer" aria-hidden="true" />

          <div className="hero-phone" id="heroPhone">
            <div className="hp-frame">
              <div className="hp-island" />
              <div className="hp-screen">
                <div className="hp-status">
                  <span>9:41</span>
                  <span className="hp-sig">
                    <i />
                    <i />
                    <i />
                    <i />
                  </span>
                </div>
                <div className="hp-head">
                  <span className="hp-back">‹</span>
                  <span className="hp-av">
                    <CashMark />
                  </span>
                  <span className="hp-id">
                    <span className="hp-nm">Cash</span>
                  </span>
                  <span className="hp-video">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="2" y="6" width="13" height="12" rx="2.5" />
                      <path d="M22 8.5l-5 3.5 5 3.5z" />
                    </svg>
                  </span>
                </div>
                <div className="hp-chat" id="hpChat" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
