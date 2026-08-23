import CashMark from './CashMark'

// "Watch it work" — a pinned Telegram thread that advances as you scroll past.
// The 300vh runway for the sticky stage lives in CSS (not an inline style) so
// the mobile breakpoint can unpin it and play the thread on a timer instead.
export default function Sequence() {
  return (
    <section id="seq">
      <div className="stage">
        <div className="seq-inner">
          <div className="seq-copy">
            <span className="eyebrow">Live on Telegram</span>
            <h2>
              One message.
              <br />
              <span className="it">Everything handled.</span>
            </h2>
            <p>
              Cash lives in Telegram. Message it like you would a teammate, and it works across
              Slack, your calendar, and everything else you already use.
            </p>
            <ul className="seq-steps" id="seqSteps" />
          </div>

          <div className="seq-phone">
            <div className="seq-scr">
              <div className="seq-isl" />

              <div className="ios-bar" aria-hidden="true">
                <span>9:41</span>
                <span className="ico">
                  <svg viewBox="0 0 18 12" fill="currentColor">
                    <rect x="0" y="7" width="3" height="5" rx="1" />
                    <rect x="5" y="5" width="3" height="7" rx="1" />
                    <rect x="10" y="2.5" width="3" height="9.5" rx="1" />
                    <rect x="15" y="0" width="3" height="12" rx="1" />
                  </svg>
                  <svg viewBox="0 0 25 12" fill="none" stroke="currentColor" strokeWidth="1.4">
                    <rect x=".7" y=".7" width="20" height="10.6" rx="3" />
                    <rect x="2.4" y="2.4" width="14" height="7.2" rx="1.6" fill="currentColor" stroke="none" />
                    <path d="M23 4.4v3.2" strokeLinecap="round" />
                  </svg>
                </span>
              </div>

              <div className="tg-head">
                <span className="tg-back">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M15 18l-6-6 6-6" />
                  </svg>
                </span>
                <span className="tg-av">
                  <CashMark />
                </span>
                <span className="tg-id">
                  <span className="tg-nm">
                    Cash <i className="tg-bot">bot</i>
                  </span>
                  <span className="tg-sub">online</span>
                </span>
                <span className="tg-menu" aria-hidden="true">
                  <i />
                  <i />
                  <i />
                </span>
              </div>

              <div className="seq-body" id="seqBody" />

              <div className="tg-input" aria-hidden="true">
                <span className="tg-clip">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                    <path d="M21.4 11.05l-9.2 9.2a5 5 0 01-7.07-7.08l8.49-8.48a3.33 3.33 0 014.71 4.71l-8.49 8.49a1.67 1.67 0 01-2.36-2.36l7.78-7.78" />
                  </svg>
                </span>
                <span className="tg-box">Message</span>
                <span className="tg-mic">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                    <path d="M12 2a3 3 0 00-3 3v7a3 3 0 006 0V5a3 3 0 00-3-3z" />
                    <path d="M5 11a7 7 0 0014 0M12 18v4" />
                  </svg>
                </span>
              </div>

              <div className="seq-home" />
            </div>
          </div>
        </div>

        <div className="scue" id="seqCue">
          <div className="mouse" />
          Scroll
        </div>
      </div>
    </section>
  )
}
