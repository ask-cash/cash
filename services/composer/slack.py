"""
slack.py — Slack style block + reply budget for the composer.

Slack tone differs from Discord: it is usually a work surface, so Cash is a
touch more professional and uses Slack's mrkdwn conventions (`*bold*`, not
`**bold**`). Threaded replies keep channels tidy — the Slack adapter sets
``thread_ts`` from the event's message id.
"""

PLATFORM = "slack"
# Slack accepts up to ~40k chars in a message but truncates display ~3000;
# Cash replies are short anyway. Keep a sane budget.
MAX_CHARS = 3000

STYLE = (
    "Slack style: this is a work channel, so be professional, helpful, and to "
    "the point, while staying in Cash's warm voice. Keep it to 1-3 short "
    "sentences. Use Slack mrkdwn if you format at all (*bold*, _italic_, `code`) "
    "— NOT GitHub-style double asterisks. No big headers. Match the asker's "
    "language and register."
)


def style_block() -> str:
    return STYLE
