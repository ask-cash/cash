"""
memory.py — Persistent long-term memory for the bot.
Remembers things you said days/weeks ago and can recall them.

State is tenant-scoped and persisted through services.state_store (Postgres in
prod, local files in dev) rather than raw user_data/*.json files:
  conversations  — append-only event stream of every message
  facts          — extracted facts about the user
  decisions      — things the user said they want to do
  trading_journal — trade log entries
"""

import datetime as dt
import hashlib
from typing import Optional

from services import state_store
from services.user_profile import now as ist_now, today as ist_today

NAMESPACE = "memory"

# Memory "kinds" — Cash's practical subset of the documented eight-type model.
# Facts map onto durable kinds; decisions are always prospective.
#   semantic   — stable facts about the user / their world
#   procedural — rules and how-tos ("my trading rule is …")
#   emotional  — feelings, sensitivities, what to be careful about
#   narrative  — the ongoing story of who they are
#   prospective— intentions / decisions with an expiry (decisions only)
_CATEGORY_TO_KIND = {
    "preference": "semantic",
    "person": "semantic",
    "general": "semantic",
    "rule": "procedural",
    "plan": "prospective",
    "feeling": "emotional",
}
DURABLE_KINDS = ("semantic", "procedural", "emotional", "narrative")


def _fingerprint(text: str) -> str:
    """Stable content hash for dedup — case/space-insensitive."""
    normalized = " ".join((text or "").strip().lower().split())
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


def _age_days(made_date: str) -> int:
    """Whole days since an ISO date string (best-effort; 0 on parse failure)."""
    try:
        made = dt.date.fromisoformat((made_date or "")[:10])
        return max((ist_today() - made).days, 0)
    except ValueError:
        return 0


# =====================================================================
# CONVERSATION LOG — append-only, never loses anything
# =====================================================================

def log_message(role: str, text: str, metadata: dict = None):
    """Log every single message (user or bot) with timestamp."""
    entry = {
        "timestamp": ist_now().isoformat(),
        "date": ist_today().isoformat(),
        "role": role,  # "user" or "assistant"
        "text": text,
        "metadata": metadata or {},
    }
    state_store.append_event(NAMESPACE, "conversations", entry)


def get_recent_conversations(days: int = 7, limit: int = 100) -> list[dict]:
    """Get recent conversation entries from the last N days."""
    cutoff = (ist_today() - dt.timedelta(days=days)).isoformat()
    entries = [
        e for e in state_store.read_events(NAMESPACE, "conversations")
        if e.get("date", "") >= cutoff
    ]
    return entries[-limit:]


def search_conversations(query: str, days: int = 30) -> list[dict]:
    """Search past conversations for a keyword/phrase."""
    entries = get_recent_conversations(days=days, limit=500)
    query_lower = query.lower()
    return [e for e in entries if query_lower in e.get("text", "").lower()]


# =====================================================================
# FACTS — things the bot learns about you
# =====================================================================

def _load_facts() -> list[dict]:
    return state_store.read_json(NAMESPACE, "facts", default=[])


def _save_facts(facts: list[dict]):
    state_store.write_json(NAMESPACE, "facts", facts)


def store_fact(fact: str, category: str = "general", source_message: str = "",
               kind: str = None) -> dict:
    """Store a learned fact about the user, deduped by content fingerprint.

    Returns the stored (or refreshed) record. If an equivalent fact already
    exists it is not duplicated — its ``last_seen`` is refreshed and the new
    source is attributed, so re-hearing the same thing strengthens rather than
    clutters memory.
    """
    facts = _load_facts()
    fp = _fingerprint(fact)
    for f in facts:
        if f.get("fingerprint") == fp or _fingerprint(f.get("fact", "")) == fp:
            f["last_seen"] = ist_now().isoformat()
            if source_message:
                srcs = f.setdefault("sources", [])
                if source_message not in srcs:
                    srcs.append(source_message)
            _save_facts(facts)
            return f

    entry = {
        "fact": fact,
        "category": category,  # e.g. "preference", "plan", "person", "general"
        "kind": kind or _CATEGORY_TO_KIND.get(category, "semantic"),
        "fingerprint": fp,
        "learned_on": ist_now().isoformat(),
        "source": source_message,
        "sources": [source_message] if source_message else [],
    }
    facts.append(entry)
    _save_facts(facts)
    return entry


def get_facts(category: str = None) -> list[dict]:
    """Get all stored facts, optionally filtered by category."""
    facts = _load_facts()
    if category:
        return [f for f in facts if f.get("category") == category]
    return facts


def search_facts(query: str) -> list[dict]:
    """Search facts by keyword."""
    facts = _load_facts()
    q = query.lower()
    return [f for f in facts if q in f.get("fact", "").lower()]


# =====================================================================
# DECISIONS — "today/this week I want to..." type statements
# =====================================================================

def _load_decisions() -> list[dict]:
    return state_store.read_json(NAMESPACE, "decisions", default=[])


def _save_decisions(decisions: list[dict]):
    state_store.write_json(NAMESPACE, "decisions", decisions)


def store_decision(decision: str, scope: str = "today", expires: str = None):
    """
    Store a user decision/intention.
    scope: "today", "this_week", "this_month", "permanent"
    expires: ISO date string when this decision is no longer relevant
    """
    decisions = _load_decisions()

    if not expires:
        if scope == "today":
            expires = ist_today().isoformat()
        elif scope == "this_week":
            expires = (ist_today() + dt.timedelta(days=7)).isoformat()
        elif scope == "this_month":
            expires = (ist_today() + dt.timedelta(days=30)).isoformat()
        else:
            expires = "9999-12-31"  # permanent

    fp = _fingerprint(decision)
    today = ist_today().isoformat()
    for d in decisions:
        # Dedup only against still-active, unfulfilled decisions — an expired or
        # fulfilled one with the same text is a genuinely new intention.
        if (_fingerprint(d.get("decision", "")) == fp
                and not d.get("fulfilled")
                and d.get("expires", "") >= today):
            d["restated_on"] = ist_now().isoformat()
            _save_decisions(decisions)
            return d

    entry = {
        "decision": decision,
        "scope": scope,
        "kind": "prospective",
        "fingerprint": fp,
        "made_on": ist_now().isoformat(),
        "made_date": today,
        "expires": expires,
        "fulfilled": False,
    }
    decisions.append(entry)
    _save_decisions(decisions)
    return entry


def get_active_decisions() -> list[dict]:
    """Get all decisions that haven't expired yet."""
    decisions = _load_decisions()
    today = ist_today().isoformat()
    return [d for d in decisions if d.get("expires", "") >= today]


def get_decisions_for_date(date: dt.date) -> list[dict]:
    """Get decisions made on a specific date."""
    decisions = _load_decisions()
    date_str = date.isoformat()
    return [d for d in decisions if d.get("made_date") == date_str]


def fulfill_decision(decision_text: str) -> Optional[dict]:
    """Mark a decision as fulfilled."""
    decisions = _load_decisions()
    q = decision_text.lower()
    for d in decisions:
        if q in d.get("decision", "").lower():
            d["fulfilled"] = True
            d["fulfilled_on"] = ist_now().isoformat()
            _save_decisions(decisions)
            return d
    return None


# =====================================================================
# TRADING JOURNAL
# =====================================================================

def log_trade(entry: dict):
    """Log a trade to the trading journal."""
    entry["timestamp"] = ist_now().isoformat()
    entry["date"] = ist_today().isoformat()
    state_store.append_event(NAMESPACE, "trading_journal", entry)


def get_recent_trades(days: int = 7) -> list[dict]:
    """Get trades from the last N days."""
    cutoff = (ist_today() - dt.timedelta(days=days)).isoformat()
    return [
        t for t in state_store.read_events(NAMESPACE, "trading_journal")
        if t.get("date", "") >= cutoff
    ]


# =====================================================================
# MEMORY SUMMARY — build context for Claude
# =====================================================================

def build_memory_context(days: int = 7) -> str:
    """
    Build a memory summary string to inject into Claude's context.
    This is what makes the bot 'remember' things across conversations.
    """
    sections = []

    active = get_active_decisions()
    if active:
        sections.append("ACTIVE DECISIONS & INTENTIONS:")
        for d in active[-15:]:
            status = "✓ done" if d.get("fulfilled") else "pending"
            sections.append(f"  [{d['made_date']}] ({d['scope']}) {d['decision']} — {status}")

    facts = get_facts()
    if facts:
        sections.append("\nLEARNED FACTS ABOUT USER:")
        for f in facts[-20:]:
            sections.append(f"  • {f['fact']} (learned {f['learned_on'][:10]})")

    recent = get_recent_conversations(days=days, limit=50)
    if recent:
        sections.append(f"\nRECENT CONVERSATION HIGHLIGHTS (last {days} days):")
        user_msgs = [e for e in recent if e["role"] == "user"]
        for msg in user_msgs[-20:]:
            sections.append(f"  [{msg['date']}] User: {msg['text'][:150]}")

    trades = get_recent_trades(days=7)
    if trades:
        sections.append(f"\nRECENT TRADES ({len(trades)} in last 7 days):")
        for t in trades[-5:]:
            sections.append(f"  [{t['date']}] {t.get('symbol','?')} {t.get('action','?')} — {t.get('result','?')}")

    return "\n".join(sections) if sections else "No memory yet — this is a fresh start."


# =====================================================================
# BACKFILL — classify legacy records into kinds + fingerprints (idempotent)
# =====================================================================

def backfill_kinds() -> dict:
    """Add ``kind`` + ``fingerprint`` to any pre-v2 facts/decisions.

    Idempotent: records that already carry both fields are left untouched, so it
    is safe to run repeatedly (e.g. once on deploy). Returns a small report.
    """
    facts = _load_facts()
    facts_touched = 0
    for f in facts:
        changed = False
        if not f.get("fingerprint"):
            f["fingerprint"] = _fingerprint(f.get("fact", ""))
            changed = True
        if not f.get("kind"):
            f["kind"] = _CATEGORY_TO_KIND.get(f.get("category", "general"), "semantic")
            changed = True
        facts_touched += 1 if changed else 0
    if facts_touched:
        _save_facts(facts)

    decisions = _load_decisions()
    decisions_touched = 0
    for d in decisions:
        changed = False
        if not d.get("fingerprint"):
            d["fingerprint"] = _fingerprint(d.get("decision", ""))
            changed = True
        if not d.get("kind"):
            d["kind"] = "prospective"
            changed = True
        decisions_touched += 1 if changed else 0
    if decisions_touched:
        _save_decisions(decisions)

    return {"facts_updated": facts_touched, "decisions_updated": decisions_touched}
