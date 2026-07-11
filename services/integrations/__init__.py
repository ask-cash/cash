"""
integrations — Cash's integration registry + TokenManager (Feature 7).

Public surface:
  * registry lookups (``all_providers``, ``get``, ``available_providers``,
    ``providers_unlocking``, ``connect_url``)
  * token management (``is_connected``, ``connected_providers``,
    ``credentials``, ``store_token``, ``disconnect``)
  * the link to Feature 6 skill packs (``is_pack_unlocked``,
    ``unlocked_pack_ids``, ``pack_status``): a pack is *unlocked* when at least
    one provider that unlocks it is connected.

Unlock state is intentionally **advisory** (surfaced to the dashboard + status
commands), not a hard execution gate: a capability whose integration is missing
still runs and returns Cash's friendly "connect X first" result, so the guidance
isn't lost. Hard gating stays with Feature 6's flags.
"""

from __future__ import annotations

from services.integrations.registry import (  # noqa: F401
    Provider,
    all_providers,
    get,
    available_providers,
    providers_unlocking,
    connect_url,
    register,
    AUTH_GOOGLE_OAUTH,
    AUTH_DEVICE_CODE,
    AUTH_ACCOUNT_LINK,
    AUTH_PLANNED,
)
from services.integrations.tokens import (  # noqa: F401
    is_connected,
    connected_providers,
    credentials,
    store_token,
    disconnect,
)
from services.integrations.connections import (  # noqa: F401
    set_status,
    get_status,
    status_map,
)


def mark_connected(provider_id: str) -> None:
    """Record a provider as connected for the active tenant (ledger write)."""
    set_status(provider_id, True)


def mark_disconnected(provider_id: str) -> None:
    """Record a provider as disconnected for the active tenant (ledger write)."""
    set_status(provider_id, False)


def is_pack_unlocked(pack_id: str) -> bool:
    """True if any provider that unlocks ``pack_id`` is connected.

    Packs with no owning provider (e.g. core chat, tasks, reminders) are always
    considered unlocked — they need no integration.
    """
    providers = providers_unlocking(pack_id)
    if not providers:
        return True
    return any(is_connected(p.id) for p in providers)


def unlocked_pack_ids() -> set[str]:
    """Every skill-pack id currently unlocked by a connected integration."""
    from services import skills

    return {s.id for s in skills.all_skills() if is_pack_unlocked(s.id)}


def pack_status() -> dict[str, dict]:
    """Per-pack connect status, for the dashboard / a status command.

    Maps pack id -> {"unlocked": bool, "providers": [...], "connected": [...]}.
    """
    from services import skills

    out: dict[str, dict] = {}
    for s in skills.all_skills():
        providers = providers_unlocking(s.id)
        out[s.id] = {
            "unlocked": is_pack_unlocked(s.id),
            "providers": [p.id for p in providers],
            "connected": [p.id for p in providers if is_connected(p.id)],
        }
    return out
