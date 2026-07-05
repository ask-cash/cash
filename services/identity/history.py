"""
history.py — Per-person conversation reader.

Reads the tenant-scoped conversation event stream (services.state_store,
namespace "memory", key "conversations") filtered by metadata.person_id
(stamped by handlers). In Postgres this is the `event_log` table under RLS;
locally it is a per-tenant JSONL file.
"""

import datetime as dt
import logging
import os

from services import state_store
from services.memory import NAMESPACE as MEMORY_NAMESPACE

logger = logging.getLogger(__name__)

# Back-compat constant; the actual source is now state_store events.
MEMORY_PATH = os.path.join("user_data", "memory", "conversations.jsonl")

CONVERSATIONS_KEY = "conversations"


def _all_conversations() -> list[dict]:
    try:
        return state_store.read_events(MEMORY_NAMESPACE, CONVERSATIONS_KEY)
    except Exception:
        logger.exception("[history] failed reading conversation events")
        return []


def recent_for_person(
    person_id: str,
    *,
    limit: int = 20,
    days: int = 60,
) -> list[dict]:
    """Return up to `limit` most-recent log entries for this person, oldest-first.

    Empty list on missing person_id or read error — never raises.
    """
    if not person_id:
        return []

    # Include history of any person merged into this one, so a linked identity
    # inherits its past conversations (shared memory across platforms).
    ids = {person_id}
    try:
        from services.identity.linking import merged_into
        ids |= merged_into(person_id)
    except Exception:
        logger.debug("[history] alias expansion skipped", exc_info=True)

    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat()
    matches: list[dict] = []
    for entry in _all_conversations():
        md = entry.get("metadata") or {}
        if md.get("person_id") not in ids:
            continue
        ts = entry.get("timestamp", "")
        if ts and ts < cutoff:
            continue
        matches.append(entry)

    return matches[-limit:]


def conversation_counts_by_person() -> dict[str, int]:
    """Tally how many conversation entries each person has (tenant-scoped)."""
    counts: dict[str, int] = {}
    for entry in _all_conversations():
        pid = (entry.get("metadata") or {}).get("person_id")
        if pid:
            counts[pid] = counts.get(pid, 0) + 1
    return counts


def format_for_prompt(entries: list[dict], *, max_chars: int = 200) -> str:
    """Render entries oldest-first as 'YYYY-MM-DD role: text' lines."""
    lines = []
    for e in entries:
        role = e.get("role", "?")
        text = (e.get("text") or "").strip()
        if not text:
            continue
        if len(text) > max_chars:
            text = text[: max_chars - 3] + "..."
        ts = (e.get("timestamp") or "")[:10]
        lines.append(f"[{ts}] {role}: {text}" if ts else f"{role}: {text}")
    return "\n".join(lines)
