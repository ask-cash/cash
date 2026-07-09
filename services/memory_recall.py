"""
memory_recall.py — the gated archive recall.

Cash doesn't dump history into every prompt. The brief (services.memory_brief)
carries current context; deep history is only pulled in when the guardian's
message actually reaches back — "did I say…", "you told me…", "last week…". This
mirrors the documented recall gate: a cheap language check decides whether to
search at all, and search returns at most a few source-linked bullets.

Two entry points:
  * ``should_recall(text)`` — the gate (pure, no I/O).
  * ``recall_block(text)`` — gate + search, returning a ready-to-inject
    ``<supporting_recall>`` block, or "" when the gate is closed or nothing hits.
"""

from __future__ import annotations

import re

from services import memory

# Language that signals the user is referencing the past. Kept deliberately
# tight — a false "yes" only costs a keyword search; a false "no" just means no
# extra recall that turn (the brief still carries current context).
_PAST_REFERENCE = re.compile(
    r"\b("
    r"did i|didn'?t i|have i|had i|was i|were we|"
    r"you said|i said|i told you|you told me|we (?:said|agreed|decided|discussed)|"
    r"remember|recall|forget|"
    r"last (?:time|week|month|year|night)|earlier|before|previously|"
    r"the other day|a (?:while|few days) ago|back (?:then|when)|used to"
    r")\b",
    re.IGNORECASE,
)

_MAX_HITS = 3
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "did", "i", "you", "we", "me", "my",
    "to", "of", "in", "on", "for", "is", "was", "were", "do", "does", "have",
    "had", "said", "told", "that", "this", "it", "what", "when", "about", "with",
    "remember", "recall", "ago", "last", "week", "month", "earlier",
}


def should_recall(text: str) -> bool:
    """Cheap gate: does this message reach into the past at all?"""
    return bool(_PAST_REFERENCE.search(text or ""))


def _keywords(text: str) -> list[str]:
    # >=3 chars keeps short-but-meaningful tokens like "mom", "gym", "buy" while
    # stopwords strip the common filler. Two-letter tokens are almost all noise.
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [w for w in words if len(w) >= 3 and w not in _STOPWORDS]


def recall(query: str, limit: int = _MAX_HITS) -> list[dict]:
    """Return up to ``limit`` source-linked history bullets matching ``query``.

    Searches facts, past decisions, and the conversation archive, scoring each
    candidate by keyword overlap (ties broken by recency). Returns [] on no hit.
    Each bullet: ``{"text", "source", "type"}``.
    """
    keywords = _keywords(query)
    if not keywords:
        return []

    candidates: list[dict] = []

    for f in memory.get_facts():
        candidates.append({
            "text": f.get("fact", ""),
            "date": (f.get("learned_on") or "")[:10],
            "type": "fact",
        })
    for d in memory._load_decisions():
        candidates.append({
            "text": d.get("decision", ""),
            "date": d.get("made_date", ""),
            "type": "decision",
        })
    for c in memory.get_recent_conversations(days=90, limit=500):
        if c.get("role") == "user":
            candidates.append({
                "text": c.get("text", ""),
                "date": c.get("date", ""),
                "type": "conversation",
            })

    scored: list[tuple[int, str, dict]] = []
    for cand in candidates:
        haystack = cand["text"].lower()
        overlap = sum(1 for k in keywords if k in haystack)
        if overlap:
            scored.append((overlap, cand["date"], cand))

    # Highest overlap first, then most recent.
    scored.sort(key=lambda s: (s[0], s[1]), reverse=True)

    hits: list[dict] = []
    seen: set[str] = set()
    for _, _, cand in scored:
        key = cand["text"].strip().lower()[:120]
        if key in seen:
            continue
        seen.add(key)
        hits.append({
            "text": cand["text"][:220],
            "source": cand["date"] or "unknown date",
            "type": cand["type"],
        })
        if len(hits) >= limit:
            break
    return hits


def recall_block(query: str) -> str:
    """Gate + search → a ``<supporting_recall>`` block, or "" if nothing to add."""
    if not should_recall(query):
        return ""
    hits = recall(query)
    if not hits:
        return ""
    lines = ["<supporting_recall>"]
    for h in hits:
        lines.append(f"  • {h['text']} (from {h['source']})")
    lines.append("</supporting_recall>")
    return "\n".join(lines)
