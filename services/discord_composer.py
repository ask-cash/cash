"""
discord_composer.py — LLM-composed proxy reply for Cash on Discord.

Called from the responder after we've decided to send (queue still pending,
late-cancel check passed). Returns a structured dict that the responder
either sends or skips:

    {
      "reply": str,                # the final reply text
      "should_send": bool,         # composer self-veto if message looks sensitive
      "reason_if_skip": str        # human-readable veto reason
    }

This module is synchronous; call it via asyncio.to_thread from async code.
"""

import datetime as dt
import json
import logging
import os
from typing import Optional

import anthropic

from services.availability import AvailabilityReason, format_local_time
from services.discord_queue import PendingReply
from services.user_profile import now as ist_now

logger = logging.getLogger(__name__)

# Haiku is the right tool for short, structured proxy replies — fast and cheap.
PROXY_MODEL = "claude-haiku-4-5"

PROXY_SYSTEM = """You are Cash — Suhail's professional AI assistant. Right now you are replying ON BEHALF of Suhail in a Discord channel because someone @-mentioned him 30+ minutes ago and he hasn't responded.

RULES:
- Make it CLEAR you're Cash answering, not Suhail. Open with something like "Cash here on Suhail's behalf —".
- Keep it SHORT — at most TWO short sentences, ideally one. Discord, not Telegram. No headers, no bullets, no markdown blocks.
- LANGUAGE: match the asker's language. If the original message is in Hinglish (Hindi-English mix in Latin letters, e.g. "kal milega kya?", "bhai free ho?"), reply in Hinglish. If in plain English, reply in English. Do NOT translate to formal Hindi or Devanagari.
- Use the AVAILABILITY REASON below to explain why Suhail isn't responding:
    - If `busy=true` and `label="off the clock"` → say he's off the clock; mention `free_after_local` if present.
    - If `busy=true` with another label (e.g. "in a 1:1", "in a meeting", "on a call") → use that EXACT label. Mention `until_local` if present.
    - If `busy=false` → say he seems to be away from his desk.
  Do NOT invent details that aren't in the reason. Do NOT name specific events, attendees, or topics — only the coarse label provided.
- Offer a concrete next step: "I'll nudge him when he's free", "ping him on Telegram if urgent", etc.
- Stay in your voice — professional, warm, and concise.
- Address the asker by their display name once at the start.
- DO NOT reveal Suhail's private tasks, calendar event titles, decisions, trading details, or memory beyond the AVAILABILITY REASON's coarse label.

SELF-VETO: if the original message looks sensitive — HR matters, money/payments, account credentials, medical/personal content, anything that could embarrass Suhail or harm someone, anything that needs a real human decision — set "should_send": false and put a short reason in "reason_if_skip". Better to stay silent than to auto-reply. (Note: hard rules like "ignore this user" are enforced by the system before you are called, so you do not need to handle them here.)

OUTPUT — respond with ONLY this JSON object, no markdown, no backticks:

{
  "reply": "your reply here",
  "should_send": true,
  "reason_if_skip": ""
}
"""

FALLBACK_REPLY = (
    "Cash here on Suhail's behalf — he hasn't seen this yet. "
    "I'll flag it for him; if it's urgent, ping him on Telegram."
)


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def _serialize_reason(r: AvailabilityReason) -> dict:
    return {
        "busy": r.busy,
        "label": r.label,
        "until_local": format_local_time(r.until),
        "free_after_local": format_local_time(r.free_after),
        "working_hours": r.working_hours,
    }


def compose_proxy_reply(
    *,
    record: PendingReply,
    reason: AvailabilityReason,
    recent_context: Optional[list[str]] = None,
    channel_name: str = "",
    asker_history: str = "",
) -> dict:
    """Synchronous Claude call. Wrap in asyncio.to_thread from async callers.

    Returns a dict with keys: reply, should_send, reason_if_skip. Always
    returns a usable dict — Anthropic / parse failures degrade to a safe
    generic reply with should_send=true.
    """
    recent_context = recent_context or []

    mentioner_handle = f"@{record.mentioner_username}" if record.mentioner_username else ""
    user_block = (
        f"=== CURRENT TIME ===\n{ist_now().strftime('%Y-%m-%d %H:%M %A %Z')}\n\n"
        f"=== AVAILABILITY REASON ===\n{json.dumps(_serialize_reason(reason), indent=2)}\n\n"
        f"=== CHANNEL ===\n#{channel_name or 'unknown'}\n\n"
        f"=== MENTIONER (the person to address) ===\n"
        f"display_name='{record.mentioner_name}' username='{mentioner_handle}'\n\n"
        f"=== KNOWN HISTORY WITH THIS ASKER (from Suhail's prior conversations with Cash) ===\n"
        + (asker_history or "(none)")
        + "\n\n"
        f"=== ORIGINAL MESSAGE that @-mentioned Suhail ===\n{record.content}\n\n"
        f"=== RECENT CHANNEL HISTORY (oldest first, for thread context) ===\n"
        + ("\n".join(recent_context) if recent_context else "(none)")
        + "\n\nWrite a single reply on Suhail's behalf. Respond with ONLY the JSON object."
    )

    try:
        resp = _client().messages.create(
            model=PROXY_MODEL,
            max_tokens=400,
            system=[{
                "type": "text",
                "text": PROXY_SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": user_block}],
        )
    except Exception:
        logger.exception("[composer] Anthropic call failed; using fallback reply")
        return {"reply": FALLBACK_REPLY, "should_send": True, "reason_if_skip": ""}

    raw = resp.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("[composer] non-JSON response, treating as raw text reply: %r", raw[:200])
        return {
            "reply": (raw or FALLBACK_REPLY).strip(),
            "should_send": True,
            "reason_if_skip": "",
        }

    return {
        "reply": (parsed.get("reply") or FALLBACK_REPLY).strip(),
        "should_send": bool(parsed.get("should_send", True)),
        "reason_if_skip": (parsed.get("reason_if_skip") or "").strip(),
    }
