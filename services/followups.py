"""
followups.py — Cash acted; now she chases the result.

A follow-up is the lifecycle where Cash does something (or asks the guardian to),
then waits on a result or a decision and comes back to it. Distinct from a
reminder (which fires a fixed message at a fixed time): a follow-up has an open
question attached and is *resolved* when the answer arrives.

Records (tenant-scoped, namespace "followups"):
    {id, what, awaiting, due (ISO), status: "open"|"resolved", created, resolved_at?}

``sweep`` returns the open follow-ups whose ``due`` has passed — the job layer
turns those into nudges (in Cash's voice) and delivers them.
"""

from __future__ import annotations

import uuid

from services import state_store
from services.user_profile import now as _now

NAMESPACE = "followups"
KEY = "items"


def _load() -> list[dict]:
    return state_store.read_json(NAMESPACE, KEY, default=[]) or []


def _save(items: list[dict]) -> None:
    state_store.write_json(NAMESPACE, KEY, items)


def create(what: str, awaiting: str, due_iso: str) -> dict:
    """Open a follow-up. ``what`` = what Cash did; ``awaiting`` = the open question."""
    rec = {
        "id": uuid.uuid4().hex,
        "what": what,
        "awaiting": awaiting,
        "due": due_iso,
        "status": "open",
        "created": _now().isoformat(),
    }
    items = _load()
    items.append(rec)
    _save(items)
    return rec


def list_open() -> list[dict]:
    """Open follow-ups, soonest due first."""
    return sorted([r for r in _load() if r.get("status") == "open"],
                  key=lambda r: r.get("due", ""))


def resolve(followup_id: str) -> bool:
    """Mark a follow-up resolved. Returns True if it was found and open."""
    items = _load()
    for r in items:
        if r.get("id") == followup_id and r.get("status") == "open":
            r["status"] = "resolved"
            r["resolved_at"] = _now().isoformat()
            _save(items)
            return True
    return False


def resolve_matching(text: str) -> int:
    """Resolve every open follow-up whose ``what``/``awaiting`` mentions ``text``.

    Lets the brain close loops naturally ("done with the invoice") without ids.
    Returns the count resolved.
    """
    q = (text or "").strip().lower()
    if not q:
        return 0
    items = _load()
    n = 0
    for r in items:
        if r.get("status") != "open":
            continue
        if q in r.get("what", "").lower() or q in r.get("awaiting", "").lower():
            r["status"] = "resolved"
            r["resolved_at"] = _now().isoformat()
            n += 1
    if n:
        _save(items)
    return n


def sweep(now_iso: str = None) -> list[dict]:
    """Open follow-ups whose due time has passed — ready to nudge on. Pure read."""
    cutoff = now_iso or _now().isoformat()
    return [r for r in list_open() if r.get("due", "") <= cutoff]


def snooze(followup_id: str, hours: int = 6) -> None:
    """Push an open follow-up's due time forward so it re-surfaces later.

    Called after a nudge is delivered so the guardian isn't pinged every sweep;
    the loop only closes when they resolve it.
    """
    import datetime as dt

    items = _load()
    for r in items:
        if r.get("id") == followup_id and r.get("status") == "open":
            r["due"] = (_now() + dt.timedelta(hours=hours)).isoformat()
            r["nudged_at"] = _now().isoformat()
            _save(items)
            return
