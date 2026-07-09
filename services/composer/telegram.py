"""
telegram.py — Telegram style block + reply budget for the composer.

Telegram is the owner's *private* channel with Cash, so it gets the fullest
version of Cash's personality and the longest replies (briefings, multi-step
answers). This module exists for symmetry with the other surfaces and as the
home for the "owner channel" tone, per the design doc's note (§11) that the
Telegram brain should converge to the same composer shape as the platforms.

Today the main Telegram chat flow still runs through ``services.ai_brain``
(which carries the full action/tool surface). This STYLE is the canonical
Telegram tone string for any composer-routed Telegram reply (e.g. a future
``compose_for_owner``).
"""

PLATFORM = "telegram"
MAX_CHARS = 3900  # Telegram hard limit is 4096; leave headroom.

STYLE = (
    "Telegram style: this is the owner's private chat with Cash, so you can be "
    "your fullest self — the warm, sharp cat who looks after them. "
    "Address the owner by their own name (from context), never assume it. "
    "Longer answers are fine when the question warrants (briefings, schedules, "
    "multi-step help). Plain text or light Markdown. Match the owner's language, "
    "including Hinglish."
)


def style_block() -> str:
    return STYLE
