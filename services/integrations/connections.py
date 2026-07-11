"""
connections.py — the per-tenant integration connection ledger.

An explicit record of which providers a tenant has connected or disconnected,
stored in the ``integration_connections`` table (tenant-scoped; RLS on Postgres,
and every query filters by tenant_id so it's also correct on SQLite/dev).

This is the source of truth Cash checks for "is X connected for this user". It's
distinct from where the *credentials* live (OAuth tokens in the secrets vault,
account links in platform_identities): the ledger records intent/state, so a
disconnect is remembered even if a stale token or identity row lingers.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Optional

from services.db import connect
from services.tenancy import current_tenant_id

logger = logging.getLogger(__name__)

STATUS_CONNECTED = "connected"
STATUS_DISCONNECTED = "disconnected"


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def set_status(provider_id: str, connected: bool) -> None:
    """Record a provider as connected/disconnected for the active tenant."""
    tid = current_tenant_id()
    status = STATUS_CONNECTED if connected else STATUS_DISCONNECTED
    now = _now_iso()
    connected_at = now if connected else None
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO integration_connections (tenant_id, provider_id, status, connected_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (tenant_id, provider_id)
            DO UPDATE SET status = excluded.status,
                          connected_at = COALESCE(excluded.connected_at, integration_connections.connected_at),
                          updated_at = excluded.updated_at
            """,
            (tid, provider_id, status, connected_at, now),
        )


def get_status(provider_id: str) -> Optional[bool]:
    """True/False if the ledger has a record for this provider, else None."""
    tid = current_tenant_id()
    try:
        with connect() as conn:
            row = conn.execute(
                "SELECT status FROM integration_connections WHERE tenant_id = ? AND provider_id = ?",
                (tid, provider_id),
            ).fetchone()
    except Exception:
        logger.exception("[connections] get_status failed for %s", provider_id)
        return None
    if row is None:
        return None
    return row["status"] == STATUS_CONNECTED


def status_map() -> dict[str, bool]:
    """All ledger rows for the active tenant: {provider_id: connected}."""
    tid = current_tenant_id()
    try:
        with connect() as conn:
            rows = conn.execute(
                "SELECT provider_id, status FROM integration_connections WHERE tenant_id = ?",
                (tid,),
            ).fetchall()
    except Exception:
        logger.exception("[connections] status_map failed")
        return {}
    return {r["provider_id"]: (r["status"] == STATUS_CONNECTED) for r in rows}
