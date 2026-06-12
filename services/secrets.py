"""
secrets.py — Per-tenant encrypted secret/token vault.

OAuth tokens (Google, Gmail, Outlook) and other per-tenant credentials are no
longer flat files on a pod's disk — they live encrypted at rest in the
`tenant_secrets` control-plane table. Values are encrypted with Fernet using
SECRETS_ENCRYPTION_KEY (delivered via a Kubernetes Secret), so a database dump
never exposes raw tokens.

`tenant_secrets` is a control-plane table (no RLS); every query filters by the
active tenant explicitly. Local dev without a DB/key falls back to the "env"
backend so nothing breaks offline.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
from typing import Optional

from services.config import settings
from services.db import connect, is_postgres
from services.tenancy import current_tenant_id

logger = logging.getLogger(__name__)

_fernet = None


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _use_db_backend() -> bool:
    return settings.secrets_backend.lower() == "db" and bool(settings.secrets_encryption_key)


def _get_fernet():
    global _fernet
    if _fernet is None:
        from cryptography.fernet import Fernet

        _fernet = Fernet(settings.secrets_encryption_key.encode())
    return _fernet


# ---------------------------------------------------------------------------
# String secrets
# ---------------------------------------------------------------------------

def set_secret(name: str, value: str, *, tenant_id: Optional[str] = None) -> None:
    tid = tenant_id or current_tenant_id()
    if not _use_db_backend():
        logger.warning("secrets.set_secret called without db backend — value not persisted")
        return
    cipher = _get_fernet().encrypt(value.encode()).decode()
    now = _now_iso()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO tenant_secrets (tenant_id, name, cipher, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (tenant_id, name)
            DO UPDATE SET cipher = excluded.cipher, updated_at = excluded.updated_at
            """,
            (tid, name, cipher, now),
        )


def get_secret(name: str, *, tenant_id: Optional[str] = None) -> Optional[str]:
    tid = tenant_id or current_tenant_id()
    if not _use_db_backend():
        return os.getenv(name)
    with connect() as conn:
        row = conn.execute(
            "SELECT cipher FROM tenant_secrets WHERE tenant_id = ? AND name = ?",
            (tid, name),
        ).fetchone()
    if not row:
        return None
    try:
        return _get_fernet().decrypt(row["cipher"].encode()).decode()
    except Exception:
        logger.exception("Failed to decrypt secret %s for tenant %s", name, tid)
        return None


def delete_secret(name: str, *, tenant_id: Optional[str] = None) -> None:
    tid = tenant_id or current_tenant_id()
    if not _use_db_backend():
        return
    with connect() as conn:
        conn.execute(
            "DELETE FROM tenant_secrets WHERE tenant_id = ? AND name = ?",
            (tid, name),
        )


# ---------------------------------------------------------------------------
# JSON secrets (OAuth token blobs)
# ---------------------------------------------------------------------------

def set_json(name: str, value: dict, *, tenant_id: Optional[str] = None) -> None:
    set_secret(name, json.dumps(value), tenant_id=tenant_id)


def get_json(name: str, *, tenant_id: Optional[str] = None) -> Optional[dict]:
    raw = get_secret(name, tenant_id=tenant_id)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None
