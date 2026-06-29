"""
dashboard.py (service layer) — pure data + auth helpers for the management dashboard.

Deliberately imports no web framework, so the testable logic (overview assembly,
magic-link + session tokens) is unit-testable without fastapi. The FastAPI routes
and HTML rendering live in ``app/dashboard.py`` and call into here.
"""

from __future__ import annotations

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
