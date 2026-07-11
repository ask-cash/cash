"""
security.py — actor identity: resolve who Cash is talking to, once.

Every interaction resolves to exactly one actor role, and that role is what the
trust rules (services.trust) gate on:

  * guardian — the owner. Full authority.
  * trusted  — a contact the guardian explicitly granted access to.
  * unknown  — everyone else. Cannot trigger owner tools or read owner memory.

Cash's owner is authenticated at the transport edge (Telegram user id ==
owner_id), which is what ``is_owner`` on an inbound event already means. Trusted
contacts are an explicit, guardian-managed allowlist of ``person_id``s, stored in
the tenant-scoped trust namespace. Unknown is the default — the boundary fails
closed.
"""

from __future__ import annotations

from typing import Optional

from services import state_store

ROLE_GUARDIAN = "guardian"
ROLE_TRUSTED = "trusted"
ROLE_UNKNOWN = "unknown"

NAMESPACE = "trust"
_TRUSTED_KEY = "trusted_contacts"


def _trusted() -> list[str]:
    return state_store.read_json(NAMESPACE, _TRUSTED_KEY, default=[]) or []


def is_trusted(person_id: Optional[str]) -> bool:
    return bool(person_id) and person_id in _trusted()


def grant_trust(person_id: str) -> None:
    """Guardian action: add a contact to the trusted allowlist (idempotent)."""
    items = _trusted()
    if person_id not in items:
        items.append(person_id)
        state_store.write_json(NAMESPACE, _TRUSTED_KEY, items)


def revoke_trust(person_id: str) -> None:
    state_store.write_json(NAMESPACE, _TRUSTED_KEY,
                           [p for p in _trusted() if p != person_id])


def resolve_role(is_owner: bool, person_id: Optional[str] = None) -> str:
    """Resolve the actor role for an interaction. Deterministic; fails closed.

    ``is_owner`` is the authenticated owner signal from the transport edge; a
    trusted role requires an explicit allowlist entry; everyone else is unknown.
    """
    if is_owner:
        return ROLE_GUARDIAN
    if is_trusted(person_id):
        return ROLE_TRUSTED
    return ROLE_UNKNOWN
