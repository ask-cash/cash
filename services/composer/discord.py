"""
discord.py — Discord style block + reply budget for the composer.

Single source of truth for "how Cash writes on Discord". The Discord message
handler imports STYLE from here instead of keeping its own copy, so tone tweaks
land in one place across the immediate-reply and proxy-reply paths.
"""

PLATFORM = "discord"
MAX_CHARS = 1900  # Discord hard limit is 2000; leave headroom for safety.

STYLE = (
    "Discord style: professional and concise — at most 2 short sentences, ideally one. "
    "No headers, no bullet lists, no markdown code blocks unless explicitly asked. "
    "Match the asker's language: if they write Hinglish (Hindi-English mix in "
    "Latin letters, e.g. 'kaise ho', 'kal milte hain', 'bhai chill'), reply in "
    "Hinglish too. If they write English, reply in English. Don't translate to "
    "formal Hindi or Devanagari."
)


def style_block() -> str:
    return STYLE
