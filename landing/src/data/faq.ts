// FAQ entries — rendered as plain bracket-toggle rows, no accordion chrome.
export interface Faq {
  q: string
  a: string
}

export const FAQS: Faq[] = [
  {
    q: 'What is Cash, exactly?',
    a: 'A personal AI assistant with a personality — a cat — that runs your calendar, tasks, inbox and trading rules, and answers you in plain language across the apps you already use. One brain, one memory, everywhere you talk to her.',
  },
  {
    q: 'Which platforms does she work on?',
    a: 'Telegram and Discord today, with Slack and Teams via adapters. The same memory follows you across all of them — talk to Cash on Telegram, pick the thread back up on Discord.',
  },
  {
    q: 'What can she actually connect to?',
    a: 'Google Calendar, Gmail and Drive, plus Outlook calendar. Slack, Notion, HubSpot and Linear are on the way. She merges what you connect into one view and acts on it.',
  },
  {
    q: 'How does the memory work?',
    a: 'Every message is logged, and Cash extracts what matters — decisions with an expiry, permanent facts, trades. Before every reply she injects your recent memory and active decisions into context, so she genuinely remembers what you said days ago.',
  },
  {
    q: 'Is my data private?',
    a: 'Cash is single-tenant and isolated per person, with a hard credential boundary — secrets are injected at the edge and never reach the model. Hard rules ("ignore this person") are enforced structurally, before any AI is involved.',
  },
  {
    q: 'Can I get one for myself?',
    a: 'Cash works for Suhail — but she trained a whole litter. Join the waitlist and she will make an intro, or help you build one around your own schedule, platforms and rules.',
  },
]
