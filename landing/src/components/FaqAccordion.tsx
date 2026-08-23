const ITEMS: { q: string; a: string }[] = [
  {
    q: 'Is my data safe with Cash?',
    a: 'Every connection is made through secure, revocable OAuth. You grant access per tool and can pull it at any time. Cash runs in a sandboxed environment, never sells your data, and you can self-host if you prefer full control.',
  },
  {
    q: 'Does Cash act without my approval?',
    a: 'By default, Cash drafts and proposes, and you approve with one tap. You decide exactly how much autonomy to grant, from “always ask” to “handle routine things and only escalate what matters.”',
  },
  {
    q: 'Which tools does it connect to?',
    a: 'Calendar, Gmail, Slack, Telegram, Notion, GitHub, and market feeds like Coinbase, Binance, Zerodha and TradingView, with more added every week. If you live in it, Cash is working to reach it.',
  },
  {
    q: 'How is this different from a chatbot?',
    a: 'A chatbot answers when asked and forgets when closed. Cash is a persistent operating system, it remembers every decision, works across all your tools autonomously, and improves its own performance weekly.',
  },
  {
    q: 'What does it cost?',
    a: 'Cash is free to start, with paid plans for higher autonomy and volume; you cover your own API usage. Early-access members lock in founder pricing when we launch.',
  },
  {
    q: 'When can I get access?',
    a: 'We’re onboarding founders and operators in waves right now. Join the waitlist and answer a few quick questions, and we reach out the moment your spot opens.',
  },
]

// The open/close behaviour (and the max-height transition) is wired up in
// lib/faq so the panel height can be measured from the rendered DOM.
export default function FaqAccordion() {
  return (
    <section className="faq" id="faq">
      <div className="wrap">
        <div className="f-head reveal">
          <span className="eyebrow">FAQ</span>
          <h2>
            Questions, <span className="it">answered.</span>
          </h2>
          <p>Everything you might want to know before you hand Cash the keys.</p>
        </div>
        <div className="f-list reveal d1" id="faqList">
          {ITEMS.map((item) => (
            <div className="f-item" key={item.q}>
              <button className="f-q" type="button">
                {item.q}
                <span className="pm" aria-hidden="true" />
              </button>
              <div className="f-a">
                <div className="f-a-inner">{item.a}</div>
              </div>
            </div>
          ))}
        </div>
        <div className="f-foot reveal">
          Still curious? <a href="#waitlist">Ask us anything &rarr;</a>
        </div>
      </div>
    </section>
  )
}
