// Feature/benefit rows, rendered as ASCII-bracket list rows ([+]) in the
// terminal-native system. Copy tracks the product README.
export interface Feature {
  mark: string
  label: string
  desc: string
}

export const FEATURES: Feature[] = [
  {
    mark: '[+]',
    label: 'Remembers everything',
    desc: 'Tell her once — she files it forever, and brings it back on day three of the habit you swore you would keep.',
  },
  {
    mark: '[+]',
    label: 'Multi-calendar merge',
    desc: 'Google and Outlook stitched into one view, delivered every morning before you have had coffee.',
  },
  {
    mark: '[+]',
    label: 'Smart scheduling',
    desc: 'Meetings land on gym time — Cash moves the gym, resolves the conflict, and tells you what she did.',
  },
  {
    mark: '[+]',
    label: 'Daily briefings',
    desc: 'A morning wake-up and an evening wrap-up, sent automatically, in her voice — schedule, tasks, rules.',
  },
  {
    mark: '[+]',
    label: 'Inbox intelligence',
    desc: 'Watches your mail, learns what matters — "escalate investors, ignore newsletters" — and applies it every time.',
  },
  {
    mark: '[+]',
    label: 'Task tracking',
    desc: 'Unfinished tasks roll forward and follow you. No delete button — only do the thing or explain why you did not.',
  },
  {
    mark: '[+]',
    label: 'Trading rules',
    desc: 'Recites your rules before the open, logs every entry to the journal, and calls you out when you break discipline.',
  },
  {
    mark: '[+]',
    label: 'One brain, every platform',
    desc: 'Same memory across Telegram, Discord, Slack and Teams — start a thought on one, finish it on another.',
  },
]
