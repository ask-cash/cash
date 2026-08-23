import { useState } from 'react'
import { FAQS } from '../data/faq'

// FAQ rows with +/− ASCII toggle markers — plain text rows, no chevrons,
// no animated accordion chrome.
export default function Faq() {
  const [open, setOpen] = useState<number | null>(0)
  return (
    <section className="section" id="faq">
      <div className="wrap">
        <div className="sec-label">
          <span className="br">## </span>faq
        </div>
        {FAQS.map((f, i) => {
          const isOpen = open === i
          return (
            <div className={`faq-row${isOpen ? ' open' : ''}`} key={f.q}>
              <button
                className="faq-q"
                aria-expanded={isOpen}
                onClick={() => setOpen(isOpen ? null : i)}
              >
                <span className="tg" aria-hidden="true">
                  {isOpen ? '−' : '+'}
                </span>
                <span>{f.q}</span>
              </button>
              <div className="faq-a">{f.a}</div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
