"""
reminders.py — user-set one-off reminders, persisted per tenant.

A reminder is a future message Cash sends to the user *unprompted* ("ping me at
5pm"). Persistence lives in the tenant-scoped document store so reminders survive
a process restart; delivery is scheduled on the bot's JobQueue. See
``bot.handlers.messages`` (set/show + the JobQueue callback) and the poller's
boot reload in ``app.telegram_poller``.

Records are plain dicts:
    {id, text, when (ISO, tz-aware), chat_id, tenant_id, created}
"""

from __future__ import annotations

import uuid

from services import state_store
from services.tenancy import current_tenant_id
from services.user_profile import now as _now

NAMESPACE = "reminders"
KEY = "pending"


def _load() -> list[dict]:
    return state_store.read_json(NAMESPACE, KEY, default=[]) or []


def _save(items: list[dict]) -> None:
    state_store.write_json(NAMESPACE, KEY, items)


def add(text: str, when_iso: str, chat_id: int) -> dict:
    """Persist a new reminder and return the stored record."""
    rec = {
        "id": uuid.uuid4().hex,
        "text": text,
        "when": when_iso,
        "chat_id": chat_id,
        "tenant_id": current_tenant_id(),
        "created": _now().isoformat(),
    }
    items = _load()
    items.append(rec)
    _save(items)
    return rec


def remove(reminder_id: str) -> None:
    """Delete a reminder by id (no-op if already gone)."""
    _save([r for r in _load() if r.get("id") != reminder_id])


def list_pending() -> list[dict]:
    """All pending reminders for the active tenant, soonest first."""
    return sorted(_load(), key=lambda r: r.get("when", ""))
