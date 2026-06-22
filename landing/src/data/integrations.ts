// Single source of truth for the integration logos used across the hero scene,
// the phone chat, the action toasts, the scroll sequence and the marquee.
// Logos are self-hosted in /public/assets/logos.
export interface Integration {
  n: string
  src: string
}

export const INTEGR: Integration[] = [
  // inner ring — communication
  { n: 'Slack', src: '/assets/logos/slack.svg' },
  { n: 'Discord', src: '/assets/logos/discord.svg' },
  { n: 'Gmail', src: '/assets/logos/gmail.svg' },
  { n: 'Google Calendar', src: '/assets/logos/google-calendar.png' },
  { n: 'Microsoft Teams', src: '/assets/logos/microsoft-teams.png' },
  { n: 'Telegram', src: '/assets/logos/telegram.svg' },
  { n: 'Notion', src: '/assets/logos/notion.svg' },
  { n: 'GitHub', src: '/assets/logos/github.svg' },
  // outer ring — finance
  { n: 'WhatsApp', src: '/assets/logos/whatsapp.png' },
  { n: 'Coinbase', src: '/assets/logos/coinbase.png' },
  { n: 'Binance', src: '/assets/logos/binance.svg' },
  { n: 'Zerodha', src: '/assets/logos/zerodha.png' },
  { n: 'Robinhood', src: '/assets/logos/robinhood.png' },
  { n: 'MetaMask', src: '/assets/logos/metamask.svg' },
  { n: 'TradingView', src: '/assets/logos/tradingview.svg' },
]

const SRC_BY_NAME = new Map(INTEGR.map((it) => [it.n, it.src]))

/** Logo URL for a named integration (empty string if unknown). */
export const logoSrc = (name: string): string => SRC_BY_NAME.get(name) ?? ''
