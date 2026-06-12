"""
store.py — Identity/memory/behavior persistence entry point.

Historically this owned a single-tenant SQLite file. It now delegates to the
dual-engine, tenant-scoped layer in `services.db` (Postgres + RLS in prod,
SQLite locally) while preserving its public surface (`connect`, `DB_PATH`,
`ensure_schema`) so existing callers — people.py, summaries.py,
directives/store.py, scripts/backfill_identities.py — keep working unchanged.

All reads/writes are automatically scoped to the active tenant
(`services.tenancy.current_tenant_id()`); callers do not pass a tenant_id.
"""

import datetime as dt
import logging

from services.config import settings
from services.db import bootstrap, connect, reset_bootstrap_state_for_tests

logger = logging.getLogger(__name__)

# Back-compat: some scripts/tests reference DB_PATH directly.
DB_PATH = settings.sqlite_path

__all__ = ["connect", "DB_PATH", "ensure_schema", "reset_schema_state_for_tests"]


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def ensure_schema(conn=None) -> None:
    """Back-compat shim. Schema is applied by services.db.bootstrap()."""
    bootstrap()


def reset_schema_state_for_tests() -> None:
    """Test-only: clear the once-per-process schema-ready flag."""
    reset_bootstrap_state_for_tests()
