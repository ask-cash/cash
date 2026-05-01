"""
history.py — Per-person conversation reader.

For Step 4 we read user_data/memory/conversations.jsonl filtered by
metadata.person_id (stamped by handlers since Step 2). When a SQL
`conversations` table lands (Step 7's territory), this module's interface
stays the same; only the implementation moves over.
"""

import datetime as dt
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

MEMORY_PATH = os.path.join("user_data", "memory", "conversations.jsonl")


def recent_for_person(
    person_id: str,
    *,
    limit: int = 20,
    days: int = 60,
) -> list[dict]:
    """Return up to `limit` most-recent log entries for this person, oldest-first.

    Empty list on missing person_id, missing log file, or read error — never
    raises. Each entry carries the original log dict (timestamp, role, text,
    metadata, ...) so callers can format as they like.
    """
    if not person_id or not os.path.exists(MEMORY_PATH):
        return []

    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat()
    matches: list[dict] = []

    try:
        with open(MEMORY_PATH, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                md = entry.get("metadata") or {}
                if md.get("person_id") != person_id:
                    continue
                ts = entry.get("timestamp", "")
                if ts and ts < cutoff:
                    continue
                matches.append(entry)
    except Exception:
        logger.exception("[history] failed reading %s", MEMORY_PATH)
        return []

    return matches[-limit:]


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
