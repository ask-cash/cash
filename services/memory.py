"""
memory.py — Persistent long-term memory for the bot.
Remembers things you said days/weeks ago and can recall them.

Storage structure (user_data/memory/):
  conversations.jsonl   — every message exchanged (append-only log)
  facts.json            — extracted facts about the user ("I like X", "my friend Y")
  decisions.json        — things user said they want to do ("today I want to...", "this week...")
  trading_journal.json  — trade log entries
"""

import json
import os
import datetime as dt
from typing import Optional
from services.user_profile import now as ist_now, today as ist_today

MEMORY_DIR = "user_data/memory"


def _ensure_dir():
    os.makedirs(MEMORY_DIR, exist_ok=True)


# =====================================================================
# CONVERSATION LOG — append-only, never loses anything
# =====================================================================

def log_message(role: str, text: str, metadata: dict = None):
    """Log every single message (user or bot) with timestamp."""
    _ensure_dir()
    entry = {
        "timestamp": ist_now().isoformat(),
        "date": ist_today().isoformat(),
        "role": role,  # "user" or "assistant"
        "text": text,
        "metadata": metadata or {},
    }
    with open(os.path.join(MEMORY_DIR, "conversations.jsonl"), "a") as f:
        f.write(json.dumps(entry) + "\n")


def get_recent_conversations(days: int = 7, limit: int = 100) -> list[dict]:
    """Get recent conversation entries from the last N days."""
    _ensure_dir()
    path = os.path.join(MEMORY_DIR, "conversations.jsonl")
    if not os.path.exists(path):
        return []

    cutoff = (ist_today() - dt.timedelta(days=days)).isoformat()
    entries = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get("date", "") >= cutoff:
                    entries.append(entry)
            except json.JSONDecodeError:
                continue

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
    _ensure_dir()
    path = os.path.join(MEMORY_DIR, "facts.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return []


def _save_facts(facts: list[dict]):
    _ensure_dir()
    with open(os.path.join(MEMORY_DIR, "facts.json"), "w") as f:
        json.dump(facts, f, indent=2)


def store_fact(fact: str, category: str = "general", source_message: str = ""):
    """Store a learned fact about the user."""
    facts = _load_facts()
    facts.append({
        "fact": fact,
        "category": category,  # e.g. "preference", "plan", "person", "general"
        "learned_on": ist_now().isoformat(),
        "source": source_message,
    })
    _save_facts(facts)


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
    _ensure_dir()
    path = os.path.join(MEMORY_DIR, "decisions.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return []


def _save_decisions(decisions: list[dict]):
    _ensure_dir()
    with open(os.path.join(MEMORY_DIR, "decisions.json"), "w") as f:
        json.dump(decisions, f, indent=2)


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

    decisions.append({
        "decision": decision,
        "scope": scope,
        "made_on": ist_now().isoformat(),
        "made_date": ist_today().isoformat(),
        "expires": expires,
        "fulfilled": False,
    })
    _save_decisions(decisions)


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
    _ensure_dir()
    path = os.path.join(MEMORY_DIR, "trading_journal.json")
    journal = []
    if os.path.exists(path):
        with open(path) as f:
            journal = json.load(f)
    entry["timestamp"] = ist_now().isoformat()
    entry["date"] = ist_today().isoformat()
    journal.append(entry)
    with open(path, "w") as f:
        json.dump(journal, f, indent=2)


def get_recent_trades(days: int = 7) -> list[dict]:
    """Get trades from the last N days."""
    _ensure_dir()
    path = os.path.join(MEMORY_DIR, "trading_journal.json")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        journal = json.load(f)
    cutoff = (ist_today() - dt.timedelta(days=days)).isoformat()
    return [t for t in journal if t.get("date", "") >= cutoff]


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
