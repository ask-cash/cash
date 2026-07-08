"""
memory_brief.py — the compiled <memory_brief> Cash reads every turn.

This is Cash's version of the documented "brief compiler": instead of dumping raw
conversation logs into context (unbounded, noisy), we rebuild a small, current,
time-relevant snapshot each turn — open loops she's tracking, durable facts about
the guardian, and recent trades. History lives in the archive and is pulled in on
demand by ``services.memory_recall`` only when the message actually reaches back.

Pure-ish: reads through ``services.memory`` (tenant-scoped state_store) and
returns a bounded string. No LLM calls.
"""

from __future__ import annotations

from services import memory

# Hard caps so the brief stays small no matter how much history accrues.
_MAX_OPEN_LOOPS = 8
_MAX_FACTS = 10
_MAX_TRADES = 5


def build_brief() -> str:
    """Compile the current, bounded memory brief. Rebuilt fresh every turn."""
    sections: list[str] = []

    # Open loops — active, unfulfilled decisions, newest first, with their age so
    # Cash can say "day 3 of this one 👀".
    active = memory.get_active_decisions()
    open_loops = [d for d in active if not d.get("fulfilled")]
    if open_loops:
        sections.append("OPEN LOOPS (you're tracking these):")
        for d in list(reversed(open_loops))[:_MAX_OPEN_LOOPS]:
            age = memory._age_days(d.get("made_date"))
            age_str = "today" if age == 0 else f"day {age + 1}"
            sections.append(f"  • {d['decision']} ({d.get('scope', 'today')}, {age_str})")

    # Durable facts — semantic/procedural/emotional/narrative. Skip prospective
    # (those are decisions, already covered by open loops).
    facts = memory.get_facts()
    durable = [
        f for f in facts
        if f.get("kind", "semantic") in memory.DURABLE_KINDS
    ]
    if durable:
        sections.append("WHAT YOU KNOW ABOUT THEM:")
        for f in durable[-_MAX_FACTS:]:
            sections.append(f"  • {f['fact']}")

    # Recent trades — small, high-signal for a trading-focused guardian.
    trades = memory.get_recent_trades(days=7)
    if trades:
        sections.append(f"RECENT TRADES ({len(trades)} in last 7 days):")
        for t in trades[-_MAX_TRADES:]:
            sections.append(
                f"  • [{t.get('date', '?')}] {t.get('symbol', '?')} "
                f"{t.get('action', '?')} — {t.get('result', '?')}"
            )

    if not sections:
        return "No memory yet — fresh start."
    return "\n".join(sections)
