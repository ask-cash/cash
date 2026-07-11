"""
dashboard.py (service layer) — pure data + auth helpers for the management dashboard.

Deliberately imports no web framework, so the testable logic (overview assembly,
magic-link + session tokens) is unit-testable without fastapi. The FastAPI routes
and HTML rendering live in ``app/dashboard.py`` and call into here.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Optional

from services.config import settings
from services.onboarding import links
from services.tenancy import tenant_context
from services import tenant_registry
from services.identity import people as identity_people
from services.identity import history as identity_history
from services.identity.summaries import get_summary_md

logger = logging.getLogger(__name__)

SESSION_COOKIE = "cash_session"
SESSION_TTL_HOURS = 24 * 7  # a week; refreshed by re-opening a magic link
MAGIC_LINK_TTL_HOURS = 1


def make_dashboard_link(person_id: str, tenant_id: str = "default") -> str:
    """Full magic-link URL Cash hands a user to open their dashboard."""
    token = links.make_token(person_id, tenant_id=tenant_id, ttl_hours=MAGIC_LINK_TTL_HOURS)
    base = (settings.public_base_url or "").rstrip("/")
    path = f"/dashboard/login?token={token}"
    return f"{base}{path}" if base else path


def make_session_token(person_id: str, tenant_id: str = "default") -> str:
    return links.make_token(person_id, tenant_id=tenant_id, ttl_hours=SESSION_TTL_HOURS)


def session_from_token(token: Optional[str]) -> Optional[dict]:
    """Validate a session-cookie value → payload {pid, tid, exp} or None."""
    return links.verify_token(token) if token else None


def make_connect_phrase(person_id: str, tenant_id: str = "default") -> str:
    """Short-lived token a user sends to the Cash bot to prove + link an account."""
    return links.make_token(person_id, tenant_id=tenant_id, ttl_hours=MAGIC_LINK_TTL_HOURS)


def overview(person_id: str, tenant_id: str) -> dict:
    """Assemble the overview data for a person (tenant-scoped)."""
    with tenant_context(tenant_id):
        person = identity_people.get_person(person_id)
        ids = identity_people.list_platform_identities_for_person(person_id)
        tenant = tenant_registry.get_tenant(tenant_id)
        try:
            summary = get_summary_md(person_id)
        except Exception:
            summary = ""
        try:
            convo_count = len(identity_history.recent_for_person(person_id, limit=1000))
        except Exception:
            convo_count = 0
    return {
        "name": (person.canonical_name if person else None) or "there",
        "is_admin": bool(tenant and tenant.is_admin),
        "platforms": [
            {"platform": i.platform, "handle": i.handle or i.display_name or i.platform_user_id}
            for i in ids
        ],
        "summary": summary,
        "conversation_count": convo_count,
    }


# ---------------------------------------------------------------------------
# CSRF — a token bound to the session, for the chat/connect POSTs
# ---------------------------------------------------------------------------

def csrf_token(session_token: str) -> str:
    """Derive a CSRF token from the session cookie (a keyed digest of it).

    Same session → same token (embeddable in the page); a different/absent
    session can't forge it without the signing secret.
    """
    secret = links._signing_secret()  # same key that signs session tokens (bytes)
    return hmac.new(secret, (session_token or "").encode(), hashlib.sha256).hexdigest()[:32]


def verify_csrf(session_token: str, token: str) -> bool:
    return bool(token) and hmac.compare_digest(csrf_token(session_token), token)


# ---------------------------------------------------------------------------
# Connectors (Feature 7 registry + TokenManager)
# ---------------------------------------------------------------------------

def connectors_status(tenant_id: str) -> list[dict]:
    """Every provider with its live connect state, for the connectors page."""
    from services import integrations
    with tenant_context(tenant_id):
        rows = []
        for p in integrations.all_providers():
            rows.append({
                "id": p.id,
                "title": p.title,
                "available": p.available,
                "connected": integrations.is_connected(p.id),
                "unlocks": list(p.unlocks),
                "connect_hint": p.connect_hint,
            })
    return rows


def disconnect_provider(tenant_id: str, provider_id: str) -> bool:
    from services import integrations
    with tenant_context(tenant_id):
        return integrations.disconnect(provider_id)


# ---------------------------------------------------------------------------
# Preferred proactive channel (Feature 5)
# ---------------------------------------------------------------------------

def get_notify_channel(tenant_id: str) -> str:
    from services import notifications
    with tenant_context(tenant_id):
        return notifications.get_preferred_channel()


def set_notify_channel(tenant_id: str, platform: str) -> str:
    from services import notifications
    with tenant_context(tenant_id):
        notifications.set_preferred_channel(platform)
    return platform


# ---------------------------------------------------------------------------
# Memory view / redact (Feature 2)
# ---------------------------------------------------------------------------

def memory_items(tenant_id: str) -> dict:
    from services import memory
    with tenant_context(tenant_id):
        return {"facts": memory.get_facts(), "decisions": memory.get_active_decisions()}


def redact_fact(tenant_id: str, fingerprint: str) -> int:
    from services import memory
    with tenant_context(tenant_id):
        return memory.forget_fact(fingerprint)


# ---------------------------------------------------------------------------
# Web chat — the same owner brain + memory as Telegram/Discord
# ---------------------------------------------------------------------------

def _default_interpret(message: str) -> dict:
    from services.ai_brain import interpret_message
    return interpret_message(message)


def chat_reply(person_id: str, tenant_id: str, message: str, *, interpret=None) -> dict:
    """Handle one browser chat turn through the owner brain.

    Logs the turn and applies memory ops under the tenant context — the same
    path Telegram uses — so a message here and a message on Telegram share one
    memory. ``interpret`` is injectable for tests; it defaults to the real brain.
    Returns ``{"reply", "action"}``.
    """
    from services import memory, web_actions
    message = (message or "").strip()
    if not message:
        return {"reply": "", "action": "chat"}
    interpret = interpret or _default_interpret
    with tenant_context(tenant_id):
        memory.log_message("user", message,
                           metadata={"surface": "dashboard", "person_id": person_id})
        result = interpret(message) or {}
        action = result.get("action", "chat")
        reply = (result.get("reply") or "").strip()
        memory.apply_ops(result.get("memory_ops") or [])

        # Execute the action for real (calendar, tasks, reminders, memory, …) via
        # the shared executor. Its result is authoritative and replaces the LLM's
        # pre-written reply; conversational turns fall through to that reply.
        action_result = web_actions.execute(action, result.get("params") or {})
        if action_result is not None:
            reply = action_result

        memory.log_message("assistant", reply,
                           metadata={"surface": "dashboard", "person_id": person_id,
                                     "outcome": "web-chat", "action": action})
    return {"reply": reply, "action": action}
