import CashMark from './CashMark'

const LINKS = [
  { href: '#problem', label: 'Why Cash' },
  { href: '#how', label: 'How it works' },
  { href: '#seq', label: 'Integrations' },
  { href: '#faq', label: 'FAQ' },
]

// Floating glass pill. The scrolled state and the mobile drawer are wired up in
// lib/nav (the burger icon is swapped imperatively there).
export default function Nav() {
  return (
    <header className="nav" id="nav">
      <div className="nav-pill">
        <a href="#top" className="brand">
          <span className="mark">
            <CashMark />
          </span>{' '}
          Cash
        </a>
        <nav className="nav-links" id="navLinks" aria-label="Primary">
          {LINKS.map((l) => (
            <a key={l.href} href={l.href}>
              {l.label}
            </a>
          ))}
        </nav>
        <div className="nav-actions">
          <a href="#waitlist" className="btn btn-primary nav-cta">
            Get access
          </a>
        </div>
        <button className="nav-toggle" id="navToggle" aria-label="Menu" aria-expanded="false">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <line x1="3" y1="6" x2="21" y2="6" />
            <line x1="3" y1="12" x2="21" y2="12" />
            <line x1="3" y1="18" x2="21" y2="18" />
          </svg>
        </button>
      </div>
      <nav className="nav-drawer" id="navLinksMobile" aria-label="Mobile">
        {LINKS.map((l) => (
          <a key={l.href} href={l.href}>
            {l.label}
          </a>
        ))}
        <div className="nav-drawer-foot">
          <a href="#waitlist" className="btn btn-primary">
            Get access
          </a>
        </div>
      </nav>
    </header>
  )
}
