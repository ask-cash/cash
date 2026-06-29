"""
profiles.py — The CustomerProfile record.

A CustomerProfile hangs off a ``person_id`` (the canonical identity the
``services.identity`` layer resolves from a platform user id). It captures the
onboarding lifecycle and the basics we collect in chat:

    status     new -> collecting -> awaiting_setup -> active
    name, email, timezone, use_case
    integrations  {google_calendar, google_drive, gmail, ...} -> bool
    step          which question the in-chat flow is on (collecting only)

Persistence uses ``services.state_store`` (the tenant-scoped kv_documents table
in Postgres under RLS, or per-tenant JSON files locally) under the "customers"
namespace, keyed by person_id. No schema migration needed, and it inherits
tenant isolation for free.

Profiles are NOT secret (tokens live in ``services.secrets``), so the plain kv
store is the right home.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import asdict, dataclass, field
from typing import Optional

from services import state_store

logger = logging.getLogger(__name__)

NAMESPACE = "customers"

STATUS_NEW = "new"                       # never seen / no profile yet
STATUS_COLLECTING = "collecting"         # answering in-chat questions
STATUS_AWAITING_SETUP = "awaiting_setup" # link issued, web setup not done
STATUS_ACTIVE = "active"                 # fully onboarded -> assistant mode

# Ordered questions the in-chat flow asks. (field, prompt-key) — prompts live
# in flow.py so this stays data-only.
COLLECT_STEPS = ["name", "email", "timezone", "use_case"]

# Integrations the web setup step offers. Extend as connectors are added.
KNOWN_INTEGRATIONS = ["google_calendar", "google_drive", "gmail", "outlook"]


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


@dataclass
class CustomerProfile:
    person_id: str
    status: str = STATUS_NEW
    name: Optional[str] = None
    email: Optional[str] = None
    timezone: Optional[str] = None
    use_case: Optional[str] = None
    step: Optional[str] = None                       # current collect step
    integrations: dict = field(default_factory=dict) # name -> bool
    link_issued_at: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""

    @property
    def is_active(self) -> bool:
        return self.status == STATUS_ACTIVE

    @property
    def needs_onboarding(self) -> bool:
        return self.status != STATUS_ACTIVE

    def connected(self, integration: str) -> bool:
        return bool(self.integrations.get(integration))

    def to_dict(self) -> dict:
        return asdict(self)


def get_profile(person_id: str) -> Optional[CustomerProfile]:
    """Load a profile, or None if this person has never been onboarded."""
    if not person_id:
        return None
    try:
        raw = state_store.read_json(NAMESPACE, person_id, default=None)
    except Exception:
        logger.exception("[onboarding] read_json failed for %s", person_id)
        return None
    if not raw:
        return None
    # Tolerate extra/missing keys across versions.
    known = {f for f in CustomerProfile.__dataclass_fields__}  # type: ignore[attr-defined]
    data = {k: v for k, v in raw.items() if k in known}
    data.setdefault("person_id", person_id)
    return CustomerProfile(**data)


def save_profile(profile: CustomerProfile) -> CustomerProfile:
    """Persist a profile (upsert). Stamps created_at/updated_at."""
    now = _now_iso()
    if not profile.created_at:
        profile.created_at = now
    profile.updated_at = now
    try:
        state_store.write_json(NAMESPACE, profile.person_id, profile.to_dict())
    except Exception:
        logger.exception("[onboarding] write_json failed for %s", profile.person_id)
    return profile


def get_or_create(person_id: str) -> CustomerProfile:
    """Return the existing profile or a fresh STATUS_NEW one (persisted)."""
    existing = get_profile(person_id)
    if existing is not None:
        return existing
    profile = CustomerProfile(person_id=person_id, status=STATUS_NEW)
    return save_profile(profile)


def is_registered(person_id: str) -> bool:
    """True only when the person has completed onboarding (assistant mode)."""
    p = get_profile(person_id)
    return bool(p and p.is_active)


def mark_integration_connected(person_id: str, integration: str) -> Optional[CustomerProfile]:
    """Record that a person connected an integration. Returns updated profile."""
    p = get_profile(person_id)
    if p is None:
        return None
    p.integrations[integration] = True
    return save_profile(p)


def mark_active(person_id: str) -> Optional[CustomerProfile]:
    """Flip a profile to active (web setup finished). Returns updated profile."""
    p = get_profile(person_id)
    if p is None:
        return None
    p.status = STATUS_ACTIVE
    return save_profile(p)
