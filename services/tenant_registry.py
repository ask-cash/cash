"""
tenant_registry.py — Control-plane CRUD for tenants and their platform bots.

This is the multi-tenant directory the edge uses to answer two questions:
  * "An update just arrived on this Telegram bot token / Discord bot — which
     tenant does it belong to?"  -> resolve_tenant_by_token / list_bots
  * "Spin up Cash for tenant X" -> ensure_tenant

Tables (`tenants`, `tenant_bots`) are control-plane and intentionally NOT under
RLS, since the gateway must look up a tenant *before* it knows which tenant it
is. Bot tokens are matched by a salted hash so the raw token never sits in a
WHERE clause / query log; the raw token (needed to call the platform API) is
stored encrypted via services.secrets.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
import secrets as _secrets
from dataclasses import dataclass
from typing import Optional

from services.config import settings
from services.db import connect
from services import secrets as secret_vault

logger = logging.getLogger(__name__)


@dataclass
class TenantRecord:
    tenant_id: str
    display_name: str
    timezone: str
    status: str


@dataclass
class BotRecord:
    tenant_id: str
    platform: str
    external_bot_id: str


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _token_hash(token: str) -> str:
    """Stable, non-reversible token fingerprint for lookups."""
    salt = settings.secrets_encryption_key or "cash-static-salt"
    return hashlib.sha256(f"{salt}:{token}".encode()).hexdigest()


# ---------------------------------------------------------------------------
# Tenants
# ---------------------------------------------------------------------------

def ensure_tenant(
    tenant_id: str,
    *,
    display_name: str = "",
    timezone: str = "Asia/Kolkata",
) -> None:
    now = _now_iso()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO tenants (tenant_id, display_name, timezone, status, created_at)
            VALUES (?, ?, ?, 'active', ?)
            ON CONFLICT (tenant_id) DO NOTHING
            """,
            (tenant_id, display_name or tenant_id, timezone, now),
        )


def get_tenant(tenant_id: str) -> Optional[TenantRecord]:
    with connect() as conn:
        row = conn.execute(
            "SELECT tenant_id, display_name, timezone, status FROM tenants WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
    if not row:
        return None
    return TenantRecord(row["tenant_id"], row["display_name"], row["timezone"], row["status"])


def list_tenants(active_only: bool = True) -> list[TenantRecord]:
    sql = "SELECT tenant_id, display_name, timezone, status FROM tenants"
    if active_only:
        sql += " WHERE status = 'active'"
    sql += " ORDER BY created_at"
    with connect() as conn:
        rows = conn.execute(sql).fetchall()
    return [TenantRecord(r["tenant_id"], r["display_name"], r["timezone"], r["status"]) for r in rows]


def new_tenant_id() -> str:
    return "tnt_" + _secrets.token_hex(6)


# ---------------------------------------------------------------------------
# Platform bots (Telegram / Discord tokens)
# ---------------------------------------------------------------------------

def register_bot(
    *,
    tenant_id: str,
    platform: str,
    token: str,
    external_bot_id: str = "",
) -> None:
    """Associate a bot token with a tenant.

    The raw token is encrypted in the secret vault under
    "<platform>_bot_token"; only its salted hash is indexed here.
    """
    now = _now_iso()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO tenant_bots (tenant_id, platform, token_hash, external_bot_id, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (platform, token_hash)
            DO UPDATE SET tenant_id = excluded.tenant_id,
                          external_bot_id = excluded.external_bot_id
            """,
            (tenant_id, platform, _token_hash(token), external_bot_id, now),
        )
    secret_vault.set_secret(f"{platform}_bot_token", token, tenant_id=tenant_id)


def resolve_tenant_by_token(platform: str, token: str) -> Optional[str]:
    """Map an inbound platform bot token to its tenant_id (or None)."""
    with connect() as conn:
        row = conn.execute(
            "SELECT tenant_id FROM tenant_bots WHERE platform = ? AND token_hash = ?",
            (platform, _token_hash(token)),
        ).fetchone()
    return row["tenant_id"] if row else None


def list_bots(platform: str) -> list[BotRecord]:
    """Every registered bot for a platform (used by the Discord connector)."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT tenant_id, platform, external_bot_id FROM tenant_bots WHERE platform = ?",
            (platform,),
        ).fetchall()
    return [BotRecord(r["tenant_id"], r["platform"], r["external_bot_id"] or "") for r in rows]


def get_bot_token(tenant_id: str, platform: str) -> Optional[str]:
    """Fetch the raw (decrypted) bot token for a tenant/platform."""
    return secret_vault.get_secret(f"{platform}_bot_token", tenant_id=tenant_id)
