export default function Footer() {
  const socials = [
    { icon: 'https://cdn.simpleicons.org/telegram/a3a3a3', alt: 'Telegram' },
    { icon: 'https://cdn.simpleicons.org/x/a3a3a3', alt: 'X' },
    { icon: 'https://cdn.simpleicons.org/github/a3a3a3', alt: 'GitHub' },
  ]

  return (
    <footer className="border-t border-border-subtle">
      <div className="max-w-6xl mx-auto px-6 py-10 flex flex-col md:flex-row justify-between items-center gap-6">
        <div className="flex items-center gap-6">
          <span className="text-sm font-semibold flex items-center gap-1.5">
            <span>😼</span> Cash
          </span>
          <span className="text-xs text-text-tertiary">
            Built with love and 4:30 AM energy by Suhail
          </span>
        </div>

        <div className="flex items-center gap-6">
          <a className="text-xs text-text-tertiary hover:text-text transition-colors duration-200" href="#">Terms</a>
          <a className="text-xs text-text-tertiary hover:text-text transition-colors duration-200" href="#">Privacy</a>
          <div className="flex gap-3">
            {socials.map((s) => (
              <a
                key={s.alt}
                href="#"
                aria-label={s.alt}
                className="w-8 h-8 rounded-full border border-border-subtle flex items-center justify-center hover:border-border transition-all duration-200"
              >
                <img src={s.icon} alt={s.alt} className="w-3.5 h-3.5" loading="lazy" />
              </a>
            ))}
          </div>
        </div>
      </div>
    </footer>
  )
}
