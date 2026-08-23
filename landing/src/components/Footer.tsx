import footerMarkDots from '../assets/footer-mark-dots.svg?raw'

const EMAIL = 'me@whysuhail.xyz'

const PRODUCT = [
  { href: '#problem', label: 'Why Cash' },
  { href: '#how', label: 'How it works' },
  { href: '#seq', label: 'Integrations' },
  { href: '#compare', label: 'Comparison' },
  { href: '#faq', label: 'FAQ' },
]

const COMPANY = [
  { href: '#waitlist', label: 'Get access' },
  { href: `mailto:${EMAIL}`, label: 'Contact' },
]

const FIND_US = [
  { href: '#waitlist', label: 'Telegram' },
  { href: `mailto:${EMAIL}`, label: 'Email' },
]

function Column({ title, links }: { title: string; links: { href: string; label: string }[] }) {
  return (
    <div className="ft-col">
      <h4 className="ft-h">
        <i />
        {title}
      </h4>
      {links.map((l) => (
        <a href={l.href} key={l.label}>
          {l.label} <span className="ft-ar">→</span>
        </a>
      ))}
    </div>
  )
}

// Dark closing slab. The dot-matrix "cash" wordmark scatters in on reveal and
// then drifts / pushes away from the cursor — see lib/footerMark.
export default function Footer() {
  return (
    <footer>
      <div className="wrap">
        <div className="ft-grid">
          <div className="ft-say">
            <h4 className="ft-h">
              <i />
              EVERYTHING ELSE, HANDLED
            </h4>
            <p>Cash runs your calendar, your inbox and your markets from a single Telegram thread.</p>
            <a href="#waitlist" className="ft-cta">
              GET ACCESS <span className="ft-ar">→</span>
            </a>
          </div>

          <div className="ft-cols">
            <Column title="PRODUCT" links={PRODUCT} />
            <Column title="COMPANY" links={COMPANY} />
            <Column title="FIND US" links={FIND_US} />
          </div>
        </div>
      </div>

      <svg
        className="ft-mark"
        id="ftMark"
        viewBox="0 0 2600 760"
        role="img"
        aria-label="Cash"
        dangerouslySetInnerHTML={{ __html: footerMarkDots }}
      />

      <div className="ft-base">
        <span>© 2026 Cash. All rights reserved.</span>
        <a href={`mailto:${EMAIL}`}>{EMAIL}</a>
      </div>
    </footer>
  )
}
