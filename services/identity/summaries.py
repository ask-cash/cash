"""
summaries.py — Per-person rolling summaries for prompt context.

Without this, the proxy composer's prompt grows linearly per active person
(15+ chat lines each). With this, the composer reads a 4-6 bullet summary
plus only the messages newer than the summary's `last_built_at` — bounded
token cost regardless of relationship length.

The summary itself is rebuilt by a daily background job (`rebuild_stale`)
only for people whose conversation count has grown by at least
`REBUILD_THRESHOLD_MESSAGES` since their last summary. People with no new
activity are skipped entirely. Idempotent — safe to run repeatedly.
"""

import datetime as dt
import logging
import os
from dataclasses import dataclass
from typing import Optional

import anthropic

from services.identity.history import (
    conversation_counts_by_person,
    format_for_prompt,
    recent_for_person,
)
from services.identity.people import get_person
from services.db import from_row
from services.identity.store import connect

logger = logging.getLogger(__name__)

SUMMARIZER_MODEL = "claude-haiku-4-5"
SUMMARIZER_MAX_INPUT_MESSAGES = 50
REBUILD_THRESHOLD_MESSAGES = 20  # rebuild if count grew by this much since last build

SUMMARIZER_SYSTEM = """You produce compact summaries of Cash's chat history with a single person.

Your output is read by another LLM (Cash itself) when composing replies. Aim for 4–6 short markdown bullets that capture:
- their tone / communication style (formal, casual, terse, hinglish, etc.)
- topics they typically discuss with Cash
- any preferences, recurring themes, or context Suhail has shared about them
- anything actionable Cash should remember (e.g. they prefer Telegram, they're in a different timezone, etc.)

Do NOT:
- include direct quotes longer than ~10 words
- speculate about facts not present in the history
- mention Suhail's private business (trading rules, calendar specifics, etc.)
- exceed ~200 tokens

Output PLAIN markdown bullets only — no preamble, no headers, no closing line."""


@dataclass
class PersonSummary:
    person_id: str
    summary_md: str
    last_built_at: str
    source_message_count: int


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def get_summary_row(person_id: str) -> Optional[PersonSummary]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM person_summaries WHERE person_id = ?", (person_id,),
        ).fetchone()
    return from_row(PersonSummary, row) if row else None


def get_summary_md(person_id: str) -> str:
    row = get_summary_row(person_id)
    return row.summary_md if row else ""


def _conversation_counts_by_person() -> dict[str, int]:
    """Tally of how many conversation entries each person has (tenant-scoped)."""
    return conversation_counts_by_person()


def build_for_person(person_id: str) -> Optional[str]:
    """Build (or rebuild) a summary for a single person. Returns the summary_md.

    Synchronous Haiku call; wrap in asyncio.to_thread from async callers. The
    function persists the summary even if the LLM returns a short string —
    the daily job is the right place to short-circuit on too-little-data,
    not here.
    """
    person = get_person(person_id)
    if person is None:
        logger.warning("[summaries] no person row for %s — skipping", person_id)
        return None

    entries = recent_for_person(
        person_id, limit=SUMMARIZER_MAX_INPUT_MESSAGES, days=180,
    )
    if not entries:
        logger.info("[summaries] no entries for %s — nothing to summarize", person_id)
        return None

    formatted = format_for_prompt(entries, max_chars=300)
    name = person.canonical_name or person_id
    user_block = (
        f"Person: {name} ({person_id})\n"
        f"Message count in this batch: {len(entries)}\n\n"
        f"=== History (oldest → newest) ===\n{formatted}"
    )

    try:
        resp = _client().messages.create(
            model=SUMMARIZER_MODEL,
            max_tokens=400,
            system=[{
                "type": "text",
                "text": SUMMARIZER_SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": user_block}],
        )
    except Exception:
        logger.exception("[summaries] Anthropic call failed for %s", person_id)
        return None

    summary = resp.content[0].text.strip()
    if not summary:
        logger.warning("[summaries] empty summary returned for %s", person_id)
        return None

    now = _now_iso()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO person_summaries (person_id, summary_md, last_built_at, source_message_count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(tenant_id, person_id) DO UPDATE SET
                summary_md           = excluded.summary_md,
                last_built_at        = excluded.last_built_at,
                source_message_count = excluded.source_message_count
            """,
            (person_id, summary, now, len(entries)),
        )
    logger.info("[summaries] built for %s (%d messages → %d chars)",
                person_id, len(entries), len(summary))
    return summary


def rebuild_stale(threshold: int = REBUILD_THRESHOLD_MESSAGES) -> int:
    """Refresh summaries for people whose conversation count grew by ≥ threshold.

    Idempotent. Returns the number of summaries (re)built. Designed for a
    daily scheduler job. Reads `metadata.person_id` from the JSONL log to
    decide which people are worth rebuilding.
    """
    counts = _conversation_counts_by_person()
    if not counts:
        return 0

    with connect() as conn:
        existing = {
            row["person_id"]: row["source_message_count"]
            for row in conn.execute(
                "SELECT person_id, source_message_count FROM person_summaries"
            ).fetchall()
        }

    rebuilt = 0
    for person_id, current in counts.items():
        previous = existing.get(person_id, 0)
        if current - previous < threshold:
            continue
        try:
            if build_for_person(person_id):
                rebuilt += 1
        except Exception:
            logger.exception("[summaries] build_for_person failed for %s", person_id)
    logger.info("[summaries] rebuild_stale processed %d people, rebuilt %d", len(counts), rebuilt)
    return rebuilt
