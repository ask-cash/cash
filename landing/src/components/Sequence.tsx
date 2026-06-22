// Scroll-driven app sequence. The card/finale/scatter are driven imperatively
// by lib/sequence, which clones the live hero scene so positions match exactly.
export default function Sequence() {
  return (
    <section id="seq">
      <div className="stage">
        <div className="seq-scatter" id="seqScatter" aria-hidden="true" />
        <span className="eyebrow seq-eyebrow reveal">Watch it work</span>
        <div className="card" id="seqCard">
          <div className="logo" id="seqLogo">
            <img id="seqLogoImg" alt="" />
          </div>
          <div className="msg" id="seqMsg">
            <div className="app" id="seqApp" />
            <div className="t" id="seqTitle" />
            <div className="s" id="seqSub" />
          </div>
          <div className="bubbles" id="seqBubbles" style={{ display: 'none' }} />
        </div>
        <div className="finale" id="seqFinale" style={{ opacity: 0 }} />
        <div className="scue" id="seqCue">
          <div className="mouse" />
          Scroll
        </div>
      </div>
    </section>
  )
}
