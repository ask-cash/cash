import CashMark from './CashMark'

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
          <a href="#intmarq">Integrations</a>
          <a href="#ethos">Use Cases</a>
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
        <a href="#seq">Integrations</a>
        <a href="#ethos">Use Cases</a>
        <div className="nav-drawer-foot">
          <a href="#waitlist" className="btn btn-primary">
            Get access
          </a>
        </div>
      </nav>
    </header>
  )
}
