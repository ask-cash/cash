"""
cards.py — platform-agnostic rich message cards.

A card is a small structured message — a title, a body, an optional footer, and
rows of buttons — that each platform renders in its own idiom: Telegram gets an
inline keyboard, Discord gets an embed. Feature code builds a ``Card`` (or one of
the ready-made builders) and hands it to a platform adapter; it never assembles
inline keyboards or embeds by hand.

Buttons carry a semantic ``action`` + short ``arg`` (e.g. approve / deny /
task_done + an id). ``encode_callback`` / ``decode_callback`` pack that into the
``callback_data`` string handlers dispatch on, staying within Telegram's 64-byte
limit. This module is pure data — no telegram/discord imports — so it unit-tests
without a client; the thin platform glue lives in the handlers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Callback wire format: "card:<action>:<arg>". Telegram caps callback_data at 64
# bytes, so keep actions short and args to ids.
CALLBACK_PREFIX = "card"
_MAX_CALLBACK_BYTES = 64


@dataclass(frozen=True)
class Button:
    label: str          # what the user sees
    action: str         # semantic action a handler dispatches on
    arg: str = ""       # short parameter (usually an id)


@dataclass
class Card:
    title: str
    body: str = ""
    button_rows: list[list[Button]] = field(default_factory=list)
    footer: str = ""
    emoji: str = ""


# ---------------------------------------------------------------------------
# Callback codec
# ---------------------------------------------------------------------------

def encode_callback(action: str, arg: str = "") -> str:
    """Pack (action, arg) into a callback_data string. Raises if it overflows."""
    if ":" in action:
        raise ValueError("action must not contain ':'")
    data = f"{CALLBACK_PREFIX}:{action}:{arg}"
    if len(data.encode("utf-8")) > _MAX_CALLBACK_BYTES:
        raise ValueError(
            f"callback_data too long ({len(data.encode('utf-8'))} bytes > {_MAX_CALLBACK_BYTES}): {data!r}"
        )
    return data


def decode_callback(data: str) -> Optional[tuple[str, str]]:
    """Parse a card callback_data string into (action, arg), or None if it isn't one."""
    if not data or not data.startswith(CALLBACK_PREFIX + ":"):
        return None
    parts = data.split(":", 2)
    if len(parts) != 3:
        return None
    return parts[1], parts[2]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _render_text(card: Card) -> str:
    head = f"{card.emoji} " if card.emoji else ""
    parts = [f"{head}{card.title}".strip()]
    if card.body:
        parts.append(card.body)
    if card.footer:
        parts.append(card.footer)
    return "\n\n".join(parts)


def to_telegram(card: Card) -> dict:
    """Render to a Telegram-shaped payload: plain text + an inline-keyboard spec.

    Returns ``{"text": str, "keyboard": [[{"text", "callback_data"}, ...], ...] | None}``.
    The handler turns ``keyboard`` into an InlineKeyboardMarkup — kept as plain
    dicts here so this stays import-free and testable.
    """
    keyboard = [
        [{"text": b.label, "callback_data": encode_callback(b.action, b.arg)} for b in row]
        for row in card.button_rows
    ]
    return {"text": _render_text(card), "keyboard": keyboard or None}


def to_discord(card: Card) -> dict:
    """Render to a Discord-shaped payload: an embed dict + fallback content.

    Discord interactive buttons need a live View, so buttons degrade to a hint
    line on the content — the structured card still carries them for a future
    interactive renderer.
    """
    title = f"{card.emoji} {card.title}".strip()
    embed: dict = {"title": title}
    if card.body:
        embed["description"] = card.body
    if card.footer:
        embed["footer"] = {"text": card.footer}

    content = _render_text(card)
    if card.button_rows:
        hint = " · ".join(b.label for row in card.button_rows for b in row)
        content = f"{content}\n\n[{hint}]"
    return {"content": content, "embed": embed}


# ---------------------------------------------------------------------------
# Ready-made builders for the wired surfaces
# ---------------------------------------------------------------------------

def approval_card(action_name: str, note: str = "") -> Card:
    """The 'Cash wants to run X — approve?' card (trust require_approval)."""
    body = f"I want to run “{action_name}”."
    if note:
        body += f"\n\nYou said: {note}"
    return Card(
        title="Needs your yes",
        emoji="🔐",
        body=body,
        button_rows=[[
            Button("✅ Approve", "approve", action_name),
            Button("🚫 Deny", "deny", action_name),
        ]],
        footer="Tap one — this one's held until you decide.",
    )


def tasks_card(summary: dict) -> Card:
    """Today's tasks as a card, with a done button per pending task (capped)."""
    pending = summary.get("pending", [])
    done = summary.get("done", [])
    lines = [f"□ [{t['id']}] {t['task']}" for t in pending]
    lines += [f"✅ {t['task']}" for t in done]
    body = "\n".join(lines) if lines else "Nothing on the list today. 😺"

    rows = [[Button(f"✓ {t['task'][:24]}", "task_done", str(t["id"]))] for t in pending[:8]]
    footer = f"{summary.get('done_count', 0)}/{summary.get('total', 0)} done"
    return Card(title="Today's tasks", emoji="📋", body=body, button_rows=rows, footer=footer)
