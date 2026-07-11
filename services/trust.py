"""
trust.py — trust rules v2: default-deny action authority by actor role.

Before Cash executes an owner-brain action, ``evaluate(role, action)`` decides
whether it may run autonomously (``allow``), must be refused (``deny``), or needs
the guardian's explicit yes (``require_approval``). The default policy:

  * guardian → allow everything. Under a stricter "careful" posture, sensitive
    (hard-to-undo / outward-facing) actions become require_approval instead.
  * trusted  → a small read-only allow-set; everything else denied.
  * unknown  → deny everything. They cannot trigger tools or reach owner data.

The guardian owns the rules; the assistant only reads and enforces them. Explicit
guardian overrides (set_rule) win over the defaults. Sensitive actions and the
posture are the two knobs; a one-time approval grant lets a require_approval
action through exactly once after the guardian says yes.

This is enforced *before* any LLM tool execution and is deliberately separate
from the pre-LLM directive hard-rules (services.directives), which decide whether
Cash replies at all. Trust rules decide what she may *do*.
"""

from __future__ import annotations

from typing import Optional

from services import state_store
from services.security import (  # re-export roles for callers
    ROLE_GUARDIAN,
    ROLE_TRUSTED,
    ROLE_UNKNOWN,
)
from services.user_profile import now as _now

ALLOW = "allow"
DENY = "deny"
REQUIRE_APPROVAL = "require_approval"

NAMESPACE = "trust"
_RULES_KEY = "rules"
_POSTURE_KEY = "posture"
_GRANTS_KEY = "grants"
_PENDING_KEY = "pending_approvals"

POSTURE_FULL = "full_access"
POSTURE_CAREFUL = "careful"

# Owner-brain actions that reach the outside world or are hard to undo. Under the
# "careful" posture these need a guardian yes; under "full_access" they don't.
SENSITIVE_ACTIONS = {
    "send_platform_message",
    "delete_event",
    "upload_to_drive",
    "send_file",
    "create_event",
    "create_recurring_events",
    "move_event",
    "attach_file_to_event",
    "add_trading_rule",
    "update_profile",
}

# What a trusted (non-guardian) contact may do. They converse with Cash via the
# proxy/customer path and never touch the guardian's private tools, so this is
# intentionally tiny — conversation only.
TRUSTED_ALLOW = {"chat"}


# --------------------------------------------------------------------------- #
# Posture + guardian rule overrides
# --------------------------------------------------------------------------- #

def get_posture() -> str:
    doc = state_store.read_json(NAMESPACE, _POSTURE_KEY, default={"posture": POSTURE_FULL})
    return doc.get("posture", POSTURE_FULL) if isinstance(doc, dict) else POSTURE_FULL


def set_posture(posture: str) -> None:
    if posture not in (POSTURE_FULL, POSTURE_CAREFUL):
        raise ValueError(f"unknown posture: {posture!r}")
    state_store.write_json(NAMESPACE, _POSTURE_KEY, {"posture": posture})


def _overrides() -> dict:
    return state_store.read_json(NAMESPACE, _RULES_KEY, default={}) or {}


def set_rule(role: str, action: str, decision: str) -> None:
    """Guardian override for a specific (role, action). Wins over the defaults."""
    if decision not in (ALLOW, DENY, REQUIRE_APPROVAL):
        raise ValueError(f"unknown decision: {decision!r}")
    rules = _overrides()
    rules[f"{role}:{action}"] = decision
    state_store.write_json(NAMESPACE, _RULES_KEY, rules)


def clear_rule(role: str, action: str) -> None:
    rules = _overrides()
    rules.pop(f"{role}:{action}", None)
    state_store.write_json(NAMESPACE, _RULES_KEY, rules)


# --------------------------------------------------------------------------- #
# The evaluation — pure w.r.t. state (no side effects)
# --------------------------------------------------------------------------- #

def evaluate(role: str, action: str) -> str:
    """Decide allow / deny / require_approval for (role, action). Fails closed."""
    override = _overrides().get(f"{role}:{action}")
    if override:
        return override

    if role == ROLE_GUARDIAN:
        if action in SENSITIVE_ACTIONS and get_posture() == POSTURE_CAREFUL:
            return REQUIRE_APPROVAL
        return ALLOW

    if role == ROLE_TRUSTED:
        return ALLOW if action in TRUSTED_ALLOW else DENY

    # Unknown, or any unrecognized role → deny.
    return DENY


# --------------------------------------------------------------------------- #
# Approval lifecycle — for require_approval outcomes
# --------------------------------------------------------------------------- #

def _pending() -> list[dict]:
    return state_store.read_json(NAMESPACE, _PENDING_KEY, default=[]) or []


def request_approval(role: str, action: str, note: str = "") -> dict:
    """Record that (role, action) is waiting on a guardian yes. Returns the record."""
    rec = {"role": role, "action": action, "note": note, "at": _now().isoformat()}
    items = _pending()
    items.append(rec)
    state_store.write_json(NAMESPACE, _PENDING_KEY, items)
    return rec


def list_pending() -> list[dict]:
    return _pending()


def _grants() -> list[dict]:
    return state_store.read_json(NAMESPACE, _GRANTS_KEY, default=[]) or []


def approve_latest() -> Optional[dict]:
    """Guardian says yes: turn the most recent pending request into a one-time grant.

    Returns the approved request, or None if nothing was pending.
    """
    pending = _pending()
    if not pending:
        return None
    rec = pending.pop()  # most recent
    state_store.write_json(NAMESPACE, _PENDING_KEY, pending)
    grants = _grants()
    grants.append({"role": rec["role"], "action": rec["action"]})
    state_store.write_json(NAMESPACE, _GRANTS_KEY, grants)
    return rec


def consume_grant(role: str, action: str) -> bool:
    """Spend a one-time grant for (role, action) if one exists. Returns True if used."""
    grants = _grants()
    for i, g in enumerate(grants):
        if g.get("role") == role and g.get("action") == action:
            grants.pop(i)
            state_store.write_json(NAMESPACE, _GRANTS_KEY, grants)
            return True
    return False
