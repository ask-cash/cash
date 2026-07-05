"""
parser.py — Turn Suhail's free-text instruction into a Directive proposal.

Two-stage by design:

  1. `looks_like_instruction()` — cheap regex pre-filter. Most chat messages
     don't trigger an LLM call at all. Tune the keyword set as we see misses.

  2. `parse()` — Haiku-backed structured parse. Returns a `DirectiveProposal`
     dataclass on a high-confidence parse, or `None` for "this isn't really
     an instruction." The caller decides whether to store, confirm, or fall
     through to chat.

The parser does NOT touch the database. It produces a proposal; runtime
code resolves `target_hint` against the people table, handles ambiguity,
and decides whether to issue. That separation lets the parser be tested
deterministically without a DB.
"""

import datetime as dt
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Optional

import anthropic

from services.directives.store import KNOWN_ACTIONS

logger = logging.getLogger(__name__)

PARSER_MODEL = "claude-haiku-4-5"

# Cheap pre-filter. False positives are fine (parser will return None);
# false negatives mean instructions slip through as chat. Lean toward more
# hits — Haiku is cheap, and we'd rather get a pass than miss an "ignore."
# Stems use \w* to catch tense/form variations (ignore/ignoring/ignored).
_INSTRUCTION_KEYWORDS = re.compile(
    r"\b("
    r"ignor\w*|mut(?:e|ed|ing|es)|silenc\w*|"
    r"stop\s+(?:replying|responding|answering|ignoring|muting)|"
    r"block\w*|blacklist\w*|"
    r"unmut\w*|unignor\w*|unblock\w*|"
    r"auto[\s\-]?repl\w*|canned\s+repl\w*|"
    r"priorit\w*|always\s+repl\w*"
    r")\b",
    re.IGNORECASE,
)

# What `parse()` is willing to return. "unignore" is a runtime-only pseudo-
# action (the runtime revokes matching ignore directives) — see the handler.
_PARSER_ACTIONS = KNOWN_ACTIONS | {"unignore"}

# Confidence below this → fall through to chat. The parser's "this is an
# instruction" judgment is one knob; this is the other. Tune from logs.
DEFAULT_CONFIDENCE_THRESHOLD = 0.7


PARSER_SYSTEM = """You convert the owner's free-text instructions into structured Directive proposals for the Cash assistant.

Cash uses Directives to decide how to handle messages from specific people across Discord, Slack, Microsoft Teams, and Telegram.

OUTPUT — respond with ONLY this JSON object, no markdown, no backticks:

{
  "is_instruction": true | false,
  "action": "ignore" | "auto_reply" | "prioritize" | "unignore" | null,
  "target_hint": "<display name or @handle from the text, or null for scope-only>",
  "scope_platform": "*" | "discord" | "slack" | "teams" | "telegram",
  "scope_workspace": "*" | "<workspace identifier if mentioned>",
  "scope_channel": "*" | "<channel identifier if mentioned>",
  "payload": null | {"text": "<canned reply text — only for auto_reply>"},
  "expires_at": null | "<ISO8601 UTC>",
  "confidence": 0.0..1.0,
  "notes": "<short explanation, optional>"
}

ACTION SEMANTICS:
- "ignore"     — silence the target completely. No reply, no proxy reply.
- "unignore"   — revoke any active ignore directive(s) for this target.
- "auto_reply" — when this target messages, send payload.text verbatim (skip the LLM). Requires payload.text.
- "prioritize" — soft hint to the composer that this person is high priority.

RULES:
- If the message is NOT an instruction (chat, a question, a task to do, an opinion, hypothetical talk like "I'm thinking about ignoring..."), set is_instruction=false and leave other fields null.
- Default scope is "*" (everywhere). Only narrow scope if the owner says so explicitly ("on Discord", "in #trading-room").
- For temporal phrases ("till Monday", "for a week", "until next Friday"), convert to absolute UTC ISO8601 expires_at relative to CURRENT TIME below.
- Extract target_hint VERBATIM from the text. Don't normalize, don't expand, don't invent. If the message doesn't name anyone (e.g. "ignore everyone in #spam"), target_hint=null.
- If you can't tell what action the owner wants with high confidence (>= 0.7), set is_instruction=false rather than guessing.

EXAMPLES:
- "ignore @alice on discord till next monday"
  → action=ignore, target_hint="alice", scope_platform="discord", expires_at="<next Monday>", confidence=0.95
- "auto-reply to John: 'in a meeting, back in an hour'"
  → action=auto_reply, target_hint="John", payload={"text":"in a meeting, back in an hour"}, confidence=0.95
- "stop ignoring Alice"
  → action=unignore, target_hint="Alice", confidence=0.95
- "prioritize messages from Bob"
  → action=prioritize, target_hint="Bob", confidence=0.9
- "what's the weather"
  → is_instruction=false, confidence=0.0
- "I'm thinking about ignoring Alice"
  → is_instruction=false (hypothetical, not a directive)
"""


@dataclass
class DirectiveProposal:
    action: str
    target_hint: Optional[str]
    scope_platform: str
    scope_workspace: str
    scope_channel: str
    payload: Optional[dict]
    expires_at: Optional[str]
    source_text: str
    confidence: float
    notes: str = ""


def looks_like_instruction(text: str) -> bool:
    """Cheap regex pre-filter. Call before parse() to skip the LLM on plain chat."""
    if not text:
        return False
    return bool(_INSTRUCTION_KEYWORDS.search(text))


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def parse(text: str) -> Optional[DirectiveProposal]:
    """LLM-backed parse. Returns None when the text isn't an actionable instruction.

    Synchronous; wrap with asyncio.to_thread from async callers.
    """
    if not looks_like_instruction(text):
        return None

    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    user_block = (
        f"CURRENT TIME (UTC): {now_iso}\n\n"
        f"The owner's message:\n{text}\n\n"
        f"Respond with ONLY the JSON object."
    )

    try:
        resp = _client().messages.create(
            model=PARSER_MODEL,
            max_tokens=400,
            system=[{
                "type": "text",
                "text": PARSER_SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": user_block}],
        )
    except Exception:
        logger.exception("[parser] Anthropic call failed for: %r", text[:120])
        return None

    raw = resp.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("[parser] non-JSON response: %r", raw[:200])
        return None

    if not parsed.get("is_instruction"):
        return None

    action = parsed.get("action")
    if action not in _PARSER_ACTIONS:
        logger.warning("[parser] unknown action %r — dropping", action)
        return None

    confidence = float(parsed.get("confidence") or 0.0)
    if confidence < DEFAULT_CONFIDENCE_THRESHOLD:
        logger.info(
            "[parser] confidence %.2f below threshold for %r — falling through to chat",
            confidence, text[:80],
        )
        return None

    payload = parsed.get("payload") or None
    if action == "auto_reply" and not (payload and payload.get("text")):
        logger.warning("[parser] auto_reply without payload.text — dropping")
        return None

    return DirectiveProposal(
        action=action,
        target_hint=(parsed.get("target_hint") or None),
        scope_platform=(parsed.get("scope_platform") or "*") or "*",
        scope_workspace=(parsed.get("scope_workspace") or "*") or "*",
        scope_channel=(parsed.get("scope_channel") or "*") or "*",
        payload=payload,
        expires_at=(parsed.get("expires_at") or None),
        source_text=text,
        confidence=confidence,
        notes=(parsed.get("notes") or "") or "",
    )
