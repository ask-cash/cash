"""
tenancy.py — Per-request tenant context for row-level multi-tenancy.

Cash serves many tenants from one process pool. Instead of threading a
`tenant_id` argument through every function, the active tenant is stored in a
contextvar set at the edge (gateway request, worker job, connector event,
cron fan-out). The data layer (`services.db`) reads it to scope every
connection — in Postgres via a session GUC consumed by RLS policies, in
SQLite via an explicit column filter for local dev.

This keeps the change surface small while guaranteeing isolation: a query
that forgets a WHERE clause still cannot leak across tenants because the
database enforces it.
"""

from __future__ import annotations

import contextlib
import contextvars
from dataclasses import dataclass
from typing import Iterator, Optional

from services.config import settings

_current_tenant: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "cash_current_tenant", default=None
)

# Reserved tenant used for control-plane access (tenant directory, bot lookup)
# that must happen before a real tenant is known. Control-plane tables have no
# RLS, so this id simply scopes the Postgres GUC to a value that matches no
# tenant-scoped rows.
SYSTEM_TENANT = "__system__"


@dataclass(frozen=True)
class Tenant:
    tenant_id: str
    display_name: str = ""
    timezone: str = "Asia/Kolkata"
    status: str = "active"


class TenantNotSet(RuntimeError):
    """Raised when tenant isolation is enforced but no tenant is in context."""


def set_current_tenant(tenant_id: str) -> contextvars.Token:
    """Set the active tenant; returns a token for restoring the previous value."""
    if not tenant_id:
        raise ValueError("tenant_id must be a non-empty string")
    return _current_tenant.set(tenant_id)


def reset_current_tenant(token: contextvars.Token) -> None:
    _current_tenant.reset(token)


def current_tenant_id() -> str:
    """The active tenant id.

    Falls back to the configured default when nothing is set, unless
    ENFORCE_TENANT is on (prod gateways/workers), in which case a missing
    tenant is a bug and we fail loudly.
    """
    tid = _current_tenant.get()
    if tid:
        return tid
    if settings.enforce_tenant:
        raise TenantNotSet(
            "no tenant in context — every entrypoint must call set_current_tenant()"
        )
    return settings.default_tenant_id


@contextlib.contextmanager
def tenant_context(tenant_id: str) -> Iterator[str]:
    """Scope a block of work to a tenant.

    Usage:
        with tenant_context("tnt_abc"):
            handle_update(...)
    """
    token = set_current_tenant(tenant_id)
    try:
        yield tenant_id
    finally:
        reset_current_tenant(token)


@contextlib.contextmanager
def system_context() -> Iterator[str]:
    """Scope control-plane DB access (tenant directory, token lookup)."""
    token = set_current_tenant(SYSTEM_TENANT)
    try:
        yield SYSTEM_TENANT
    finally:
        reset_current_tenant(token)
