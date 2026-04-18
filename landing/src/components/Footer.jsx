import CashMascotEmbed from './CashMascotEmbed'

const socials = [
  { icon: 'https://cdn.simpleicons.org/telegram/a8b0c0', alt: 'Telegram', href: '#' },
  { icon: 'https://cdn.simpleicons.org/x/a8b0c0', alt: 'X', href: '#' },
  { icon: 'https://cdn.simpleicons.org/github/a8b0c0', alt: 'GitHub', href: '#' },
]

export default function Footer() {
  const year = new Date().getFullYear()

  return (
    <footer className="relative border-t border-white/8">
      <div className="max-w-3xl mx-auto px-6 pt-16 pb-10 text-center">
        {/* Brand */}
        <div className="inline-flex items-center gap-2 font-display text-lg font-bold text-[#f1f3f9]">
          <CashMascotEmbed className="w-7 h-6" />
          <span>Cash</span>
        </div>
        <p className="mt-2 text-sm text-[#a8b0c0]">
          Suhail&apos;s cat. Your introduction.
        </p>

        {/* Social */}
        <div className="mt-8 flex items-center justify-center gap-2.5">
          {socials.map((s) => (
            <a
              key={s.alt}
              href={s.href}
              aria-label={s.alt}
              className="w-9 h-9 rounded-full border border-white/12 flex items-center justify-center hover:border-[#4f8eff]/45 hover:bg-white/[0.05] transition-all duration-200"
            >
              <img
                src={s.icon}
                alt={s.alt}
                className="w-3.5 h-3.5"
                loading="lazy"
              />
            </a>
          ))}
        </div>

        {/* Divider */}
        <div className="mt-12 border-t border-white/8" />

        {/* Attribution */}
        <div className="mt-10 space-y-3 text-sm text-[#a8b0c0] leading-relaxed">
          <p>
            Built by{' '}
            <a
              href="#"
              className="text-[#f1f3f9] underline decoration-white/20 underline-offset-4 hover:decoration-[#4f8eff] transition-colors"
            >
              Suhail
            </a>{' '}
            at 4:30 AM, 5th April 2026.
          </p>
          <p className="text-xs text-[#6b7480]">
            Independent project. Cash thinks for herself.
          </p>
        </div>

        {/* Copyright */}
        <p className="mt-8 text-xs text-[#6b7480]">
          © {year} Cash. Made with love and sleep deprivation.
        </p>
      </div>
    </footer>
  )
}
