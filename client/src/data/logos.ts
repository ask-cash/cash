// Provider id / platform name → self-hosted logo path (assets copied from the
// landing site). Covers both the integration-registry ids returned by the API
// and the platform names used in onboarding.
const LOGOS: Record<string, string> = {
  // registry ids
  google_calendar: '/assets/logos/google-calendar.png',
  gmail: '/assets/logos/gmail.svg',
  outlook: '/assets/logos/microsoft-teams.png',
  discord: '/assets/logos/discord.svg',
  telegram: '/assets/logos/telegram.svg',
  slack: '/assets/logos/slack.svg',
  notion: '/assets/logos/notion.svg',
  hubspot: '/assets/logos/coinbase.png',
  linear: '/assets/logos/github.svg',
  twitter: '/assets/logos/whatsapp.png',
  // onboarding platform names
  Slack: '/assets/logos/slack.svg',
  'Microsoft Teams': '/assets/logos/microsoft-teams.png',
  'Google Calendar': '/assets/logos/google-calendar.png',
  Telegram: '/assets/logos/telegram.svg',
  Discord: '/assets/logos/discord.svg',
  TradingView: '/assets/logos/tradingview.svg',
  Brokers: '/assets/logos/robinhood.png',
  Gmail: '/assets/logos/gmail.svg',
  Notion: '/assets/logos/notion.svg',
  GitHub: '/assets/logos/github.svg',
}

/** Logo URL for a provider id or platform name (empty string if unknown). */
export const logoSrc = (key: string): string => LOGOS[key] ?? ''
