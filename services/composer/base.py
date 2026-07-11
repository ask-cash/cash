"""
base.py — Shared prompt-building primitives for every platform composer.

Two responsibilities:

  1. ``build_person_context(person_id)`` — assemble the bounded per-person
     context the composer injects into a reply prompt (design doc §6, step 6):
        - the rolling ``person_summaries`` row (~200 tokens) if we have one,
        - otherwise the last N raw conversation lines for that person,
        - the person's stored preferences (language, tone, ...),
        - any soft directive hints the caller passes in (e.g. "prioritize").
     This is the cost lever from §8: summary-first keeps prompt size flat as
     Cash accumulates relationships.

  2. ``complete(...)`` — a single Anthropic call site with the prompt-cache
     boilerplate, so individual composers don't each re-implement it.

Everything except ``complete`` is pure / DB-only and unit-testable.
``render_context_block`` in particular takes a PersonContext and returns a
string with no I/O, so tests can assert on the exact prompt shape.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Haiku is the right tool for short, per-person replies — fast and cheap.
DEFAULT_MODEL = "claude-haiku-4-5"

# How many raw lines to fall back to when there is no summary yet.
FALLBACK_HISTORY_LINES = 10


@dataclass
class PersonContext:
    """Bounded context about one person, ready to drop into a prompt."""

    person_id: Optional[str]
    canonical_name: Optional[str] = None
    summary_md: str = ""
    recent_lines: str = ""           # used only when summary_md is empty
    preferences: dict = field(default_factory=dict)
    soft_hints: list[str] = field(default_factory=list)

    @property
    def has_memory(self) -> bool:
        return bool(self.summary_md or self.recent_lines)


def build_person_context(
    person_id: Optional[str],
    *,
    soft_hints: Optional[list[str]] = None,
    fallback_lines: int = FALLBACK_HISTORY_LINES,
) -> PersonContext:
    """Read the cheapest sufficient context for ``person_id``.

    Best-effort and DB-backed: a missing person or a read error yields an empty
    PersonContext rather than raising, so the composer always gets *something*.
    Synchronous — wrap in ``asyncio.to_thread`` from async callers.
    """
    ctx = PersonContext(person_id=person_id, soft_hints=list(soft_hints or []))
    if not person_id:
        return ctx

    # Imported lazily so the pure helpers in this module (render_context_block)
    # remain importable without the identity stack present.
    try:
        from services.identity import people as identity_people
        person = identity_people.get_person(person_id)
        if person is not None:
            ctx.canonical_name = person.canonical_name
            if person.preferences_json:
                try:
                    ctx.preferences = json.loads(person.preferences_json) or {}
                except (json.JSONDecodeError, TypeError):
                    logger.warning("[composer] bad preferences_json for %s", person_id)
    except Exception:
        logger.exception("[composer] get_person failed for %s", person_id)

    try:
        from services.identity import summaries as identity_summaries
        ctx.summary_md = identity_summaries.get_summary_md(person_id) or ""
    except Exception:
        logger.exception("[composer] get_summary_md failed for %s", person_id)

    if not ctx.summary_md:
        try:
            from services.identity import history as identity_history
            entries = identity_history.recent_for_person(person_id, limit=fallback_lines)
            ctx.recent_lines = identity_history.format_for_prompt(entries)
        except Exception:
            logger.exception("[composer] recent_for_person failed for %s", person_id)

    return ctx


def render_context_block(ctx: PersonContext) -> str:
    """Pure: render a PersonContext to a prompt fragment. No I/O.

    Returns '' when there's nothing useful to inject, so callers can append it
    unconditionally without producing empty headers.
    """
    sections: list[str] = []

    if ctx.canonical_name:
        sections.append(f"=== WHO YOU'RE TALKING TO ===\n{ctx.canonical_name}")

    if ctx.preferences:
        pref_lines = [f"- {k}: {v}" for k, v in ctx.preferences.items() if v not in (None, "")]
        if pref_lines:
            sections.append("=== THEIR PREFERENCES ===\n" + "\n".join(pref_lines))

    if ctx.summary_md:
        sections.append("=== WHAT YOU REMEMBER ABOUT THEM ===\n" + ctx.summary_md.strip())
    elif ctx.recent_lines:
        sections.append("=== RECENT MESSAGES WITH THEM (oldest first) ===\n" + ctx.recent_lines.strip())

    if ctx.soft_hints:
        sections.append("=== NOTES FROM SUHAIL ===\n" + "\n".join(f"- {h}" for h in ctx.soft_hints))

    return "\n\n".join(sections)


def complete(
    *,
    system: str,
    user_block: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 400,
) -> str:
    """Single Anthropic call site for composers. Returns the raw text.

    Caches the (usually large, stable) system prompt. Raises on API error — the
    caller decides how to degrade (a canned fallback line, a retry, etc.); this
    helper does not swallow failures because "silence" and "generic reply" are
    different product decisions per surface.
    """
    from services import providers

    return providers.send_message(
        "composer",
        system=system,
        cache_system=True,
        user=user_block,
        model=model,
        max_tokens=max_tokens,
    ).strip()


def strip_code_fences(raw: str) -> str:
    """Remove ```json fences some models wrap JSON in. Pure helper."""
    return (raw or "").strip().replace("```json", "").replace("```", "").strip()
