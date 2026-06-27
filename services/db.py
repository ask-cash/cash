"""
db.py — Dual-engine data layer (Postgres in prod, SQLite for local dev).

Why two engines:
  * Local development / the legacy single-tenant `main.py` keep working with
    zero infra via SQLite at user_data/cash.db.
  * Production runs managed Postgres with row-level multi-tenancy. Every
    tenant-scoped table carries a `tenant_id` and a Row-Level Security (RLS)
    policy keyed on a per-connection session GUC (`app.current_tenant`). The
    `connect()` context manager sets that GUC from `services.tenancy`, so a
    query that forgets to filter by tenant still cannot read another tenant's
    rows — the database refuses.

`connect()` is the single entry point. It yields a connection whose `.execute`
accepts the SQLite-style `?` placeholder regardless of engine (we translate to
`%s` for Postgres) and whose rows support both positional (`row[0]`) and named
(`row["col"]`, `dict(row)`) access, matching sqlite3.Row semantics.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Iterator, Optional, Sequence

from services.config import settings
from services.tenancy import current_tenant_id

logger = logging.getLogger(__name__)

_bootstrap_lock = threading.Lock()
_bootstrapped = False
_pg_pool = None  # lazy psycopg_pool.ConnectionPool


def is_postgres() -> bool:
    return settings.database_url.startswith(("postgres://", "postgresql://"))


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def from_row(cls, row):
    """Build a dataclass instance from a DB row, dropping columns the dataclass
    doesn't declare.

    The physical tables carry an internal ``tenant_id`` column (for RLS) that
    the application-layer dataclasses (Person, Directive, PlatformIdentity,
    PersonSummary) deliberately don't model. ``cls(**dict(row))`` would raise on
    that extra key for any freshly-created schema; this helper keeps the read
    path tenant-transparent. Works for both sqlite3.Row and the Postgres row
    wrapper (both expose ``.keys()`` and item access).
    """
    import dataclasses

    field_names = {f.name for f in dataclasses.fields(cls)}
    data = {k: row[k] for k in row.keys() if k in field_names}
    return cls(**data)


# ---------------------------------------------------------------------------
# Schema. Forward-only, idempotent. Two dialects share the same logical model.
# ---------------------------------------------------------------------------

# Tenant-scoped tables (RLS applies in Postgres).
_TENANT_TABLES = [
    "people",
    "platform_identities",
    "directives",
    "person_summaries",
    "kv_documents",
    "event_log",
]

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id    TEXT PRIMARY KEY,
    display_name TEXT,
    timezone     TEXT NOT NULL DEFAULT 'Asia/Kolkata',
    status       TEXT NOT NULL DEFAULT 'active',
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tenant_bots (
    tenant_id       TEXT NOT NULL,
    platform        TEXT NOT NULL,
    token_hash      TEXT NOT NULL,
    token_cipher    TEXT,
    external_bot_id TEXT,
    created_at      TEXT NOT NULL,
    PRIMARY KEY (platform, token_hash)
);

CREATE TABLE IF NOT EXISTS tenant_secrets (
    tenant_id  TEXT NOT NULL,
    name       TEXT NOT NULL,
    cipher     TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, name)
);

CREATE TABLE IF NOT EXISTS people (
    tenant_id        TEXT NOT NULL DEFAULT 'default',
    person_id        TEXT NOT NULL,
    canonical_name   TEXT,
    notes            TEXT,
    preferences_json TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    PRIMARY KEY (person_id)
);

CREATE TABLE IF NOT EXISTS platform_identities (
    tenant_id            TEXT NOT NULL DEFAULT 'default',
    platform_identity_id TEXT NOT NULL,
    person_id            TEXT NOT NULL,
    platform             TEXT NOT NULL,
    workspace_id         TEXT NOT NULL DEFAULT '',
    platform_user_id     TEXT NOT NULL,
    display_name         TEXT,
    handle               TEXT,
    first_seen           TEXT NOT NULL,
    last_seen            TEXT NOT NULL,
    PRIMARY KEY (platform_identity_id),
    UNIQUE(platform, workspace_id, platform_user_id)
);
CREATE INDEX IF NOT EXISTS idx_pi_lookup ON platform_identities(platform, workspace_id, platform_user_id);
CREATE INDEX IF NOT EXISTS idx_pi_person ON platform_identities(person_id);

CREATE TABLE IF NOT EXISTS directives (
    tenant_id        TEXT NOT NULL DEFAULT 'default',
    directive_id     TEXT NOT NULL,
    issued_by        TEXT NOT NULL,
    action           TEXT NOT NULL,
    target_person_id TEXT,
    scope_platform   TEXT NOT NULL DEFAULT '*',
    scope_workspace  TEXT NOT NULL DEFAULT '*',
    scope_channel    TEXT NOT NULL DEFAULT '*',
    payload_json     TEXT,
    expires_at       TEXT,
    source_text      TEXT,
    created_at       TEXT NOT NULL,
    revoked_at       TEXT,
    PRIMARY KEY (directive_id)
);
CREATE INDEX IF NOT EXISTS idx_dir_active ON directives(target_person_id, action, revoked_at, expires_at);
CREATE INDEX IF NOT EXISTS idx_dir_scope ON directives(scope_platform, scope_workspace, scope_channel);

CREATE TABLE IF NOT EXISTS person_summaries (
    tenant_id            TEXT NOT NULL DEFAULT 'default',
    person_id            TEXT NOT NULL,
    summary_md           TEXT NOT NULL,
    last_built_at        TEXT NOT NULL,
    source_message_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, person_id)
);

CREATE TABLE IF NOT EXISTS kv_documents (
    tenant_id  TEXT NOT NULL DEFAULT 'default',
    namespace  TEXT NOT NULL,
    doc_key    TEXT NOT NULL,
    body       TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, namespace, doc_key)
);

CREATE TABLE IF NOT EXISTS event_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id  TEXT NOT NULL DEFAULT 'default',
    namespace  TEXT NOT NULL,
    log_key    TEXT NOT NULL,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_event_log_lookup ON event_log(tenant_id, namespace, log_key, id);
"""

# Postgres dialect: BIGSERIAL, JSONB, and RLS per tenant table.
_PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id    TEXT PRIMARY KEY,
    display_name TEXT,
    timezone     TEXT NOT NULL DEFAULT 'Asia/Kolkata',
    status       TEXT NOT NULL DEFAULT 'active',
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tenant_bots (
    tenant_id       TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    platform        TEXT NOT NULL,
    token_hash      TEXT NOT NULL,
    token_cipher    TEXT,
    external_bot_id TEXT,
    created_at      TEXT NOT NULL,
    PRIMARY KEY (platform, token_hash)
);
CREATE INDEX IF NOT EXISTS idx_tenant_bots_tenant ON tenant_bots(tenant_id);

CREATE TABLE IF NOT EXISTS tenant_secrets (
    tenant_id  TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    cipher     TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, name)
);

CREATE TABLE IF NOT EXISTS people (
    tenant_id        TEXT NOT NULL DEFAULT current_setting('app.current_tenant', true),
    person_id        TEXT NOT NULL,
    canonical_name   TEXT,
    notes            TEXT,
    preferences_json TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    PRIMARY KEY (tenant_id, person_id)
);

CREATE TABLE IF NOT EXISTS platform_identities (
    tenant_id            TEXT NOT NULL DEFAULT current_setting('app.current_tenant', true),
    platform_identity_id TEXT NOT NULL,
    person_id            TEXT NOT NULL,
    platform             TEXT NOT NULL,
    workspace_id         TEXT NOT NULL DEFAULT '',
    platform_user_id     TEXT NOT NULL,
    display_name         TEXT,
    handle               TEXT,
    first_seen           TEXT NOT NULL,
    last_seen            TEXT NOT NULL,
    PRIMARY KEY (tenant_id, platform_identity_id),
    UNIQUE (tenant_id, platform, workspace_id, platform_user_id)
);
CREATE INDEX IF NOT EXISTS idx_pi_lookup ON platform_identities(tenant_id, platform, workspace_id, platform_user_id);
CREATE INDEX IF NOT EXISTS idx_pi_person ON platform_identities(tenant_id, person_id);

CREATE TABLE IF NOT EXISTS directives (
    tenant_id        TEXT NOT NULL DEFAULT current_setting('app.current_tenant', true),
    directive_id     TEXT NOT NULL,
    issued_by        TEXT NOT NULL,
    action           TEXT NOT NULL,
    target_person_id TEXT,
    scope_platform   TEXT NOT NULL DEFAULT '*',
    scope_workspace  TEXT NOT NULL DEFAULT '*',
    scope_channel    TEXT NOT NULL DEFAULT '*',
    payload_json     TEXT,
    expires_at       TEXT,
    source_text      TEXT,
    created_at       TEXT NOT NULL,
    revoked_at       TEXT,
    PRIMARY KEY (tenant_id, directive_id)
);
CREATE INDEX IF NOT EXISTS idx_dir_active ON directives(tenant_id, target_person_id, action, revoked_at, expires_at);

CREATE TABLE IF NOT EXISTS person_summaries (
    tenant_id            TEXT NOT NULL DEFAULT current_setting('app.current_tenant', true),
    person_id            TEXT NOT NULL,
    summary_md           TEXT NOT NULL,
    last_built_at        TEXT NOT NULL,
    source_message_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, person_id)
);

CREATE TABLE IF NOT EXISTS kv_documents (
    tenant_id  TEXT NOT NULL DEFAULT current_setting('app.current_tenant', true),
    namespace  TEXT NOT NULL,
    doc_key    TEXT NOT NULL,
    body       TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, namespace, doc_key)
);

CREATE TABLE IF NOT EXISTS event_log (
    id         BIGSERIAL PRIMARY KEY,
    tenant_id  TEXT NOT NULL DEFAULT current_setting('app.current_tenant', true),
    namespace  TEXT NOT NULL,
    log_key    TEXT NOT NULL,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_event_log_lookup ON event_log(tenant_id, namespace, log_key, id);
"""


def _pg_rls_statements() -> list[str]:
    """Enable RLS + a tenant-isolation policy on every tenant-scoped table."""
    stmts: list[str] = []
    for table in _TENANT_TABLES:
        stmts.append(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # FORCE so even the table owner is subject to the policy.
        stmts.append(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        stmts.append(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        stmts.append(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (tenant_id = current_setting('app.current_tenant', true)) "
            f"WITH CHECK (tenant_id = current_setting('app.current_tenant', true))"
        )
    return stmts


# ---------------------------------------------------------------------------
# Postgres row + connection wrappers
# ---------------------------------------------------------------------------

class _PgRow:
    """sqlite3.Row-compatible row: positional, named, and dict() access."""

    __slots__ = ("_cols", "_vals", "_map")

    def __init__(self, cols: Sequence[str], vals: Sequence[Any]):
        self._cols = cols
        self._vals = vals
        self._map = {c: v for c, v in zip(cols, vals)}

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._vals[key]
        return self._map[key]

    def keys(self):
        return list(self._cols)

    def get(self, key, default=None):
        return self._map.get(key, default)

    def __iter__(self):
        return iter(self._vals)


def _pg_row_factory(cursor):
    cols = [c.name for c in cursor.description] if cursor.description else []

    def make(values):
        return _PgRow(cols, values)

    return make


def _translate(sql: str) -> str:
    """SQLite '?' placeholders -> Postgres '%s'. No '?' appears in literals here."""
    return sql.replace("?", "%s")


class _PgConn:
    """Adapter exposing sqlite-style .execute()/.executescript() over psycopg."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql: str, params: Sequence[Any] = ()):
        cur = self._conn.cursor()
        cur.execute(_translate(sql), tuple(params))
        return cur

    def executescript(self, script: str):
        cur = self._conn.cursor()
        for stmt in _split_statements(script):
            cur.execute(stmt)
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()


def _split_statements(script: str) -> list[str]:
    return [s.strip() for s in script.split(";") if s.strip()]


# ---------------------------------------------------------------------------
# Bootstrap (schema migration) — runs once per process, tenant-agnostic.
# ---------------------------------------------------------------------------

def _get_pool():
    global _pg_pool
    if _pg_pool is None:
        from psycopg_pool import ConnectionPool
        from psycopg.rows import tuple_row

        def _configure(conn):
            conn.row_factory = _pg_row_factory  # type: ignore[assignment]

        _pg_pool = ConnectionPool(
            settings.database_url,
            min_size=1,
            max_size=int(os.getenv("PG_POOL_MAX", "10")),
            configure=_configure,
            open=True,
        )
    return _pg_pool


def bootstrap() -> None:
    """Create schema + RLS. Idempotent; safe to call from every process."""
    global _bootstrapped
    if _bootstrapped:
        return
    with _bootstrap_lock:
        if _bootstrapped:
            return
        if is_postgres():
            _bootstrap_postgres()
        else:
            _bootstrap_sqlite()
        _bootstrapped = True


def _bootstrap_sqlite() -> None:
    os.makedirs(os.path.dirname(settings.sqlite_path) or ".", exist_ok=True)
    conn = sqlite3.connect(settings.sqlite_path, timeout=10.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SQLITE_SCHEMA)
        conn.commit()
    finally:
        conn.close()
    logger.info("[db] SQLite schema ready at %s", settings.sqlite_path)


# Arbitrary constant identifying the bootstrap DDL critical section. All roles
# use the same key so only one runs schema/RLS DDL at a time.
_BOOTSTRAP_LOCK_KEY = 911_002_001


def _bootstrap_postgres() -> None:
    pool = _get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            # Serialize bootstrap across processes. When several roles
            # (gateway/worker/connector/telegram) start at once, running the
            # RLS DDL (ALTER TABLE ... ENABLE RLS / CREATE POLICY on the same
            # tables) concurrently deadlocks. A transaction-scoped advisory lock
            # makes the others wait, then run the idempotent DDL as a no-op.
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (_BOOTSTRAP_LOCK_KEY,))
            for stmt in _split_statements(_PG_SCHEMA):
                cur.execute(stmt)
            for stmt in _pg_rls_statements():
                cur.execute(stmt)
        conn.commit()
    logger.info("[db] Postgres schema + RLS ready")


# ---------------------------------------------------------------------------
# connect() — the single entry point used by every store module.
# ---------------------------------------------------------------------------

@contextmanager
def connect() -> Iterator[Any]:
    """Yield a tenant-scoped DB connection.

    Postgres: a pooled connection with `app.current_tenant` set to the active
    tenant so RLS policies apply. SQLite: the local file connection (single
    tenant for dev). Commits on clean exit, rolls back on exception.
    """
    bootstrap()
    if is_postgres():
        yield from _connect_postgres()
    else:
        yield from _connect_sqlite()


def _connect_postgres() -> Iterator[_PgConn]:
    pool = _get_pool()
    tenant = current_tenant_id()
    with pool.connection() as conn:
        try:
            with conn.cursor() as cur:
                # is_local=true scopes the GUC to this transaction only.
                cur.execute(
                    "SELECT set_config('app.current_tenant', %s, true)", (tenant,)
                )
            yield _PgConn(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def _connect_sqlite() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(settings.sqlite_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def reset_bootstrap_state_for_tests() -> None:
    global _bootstrapped
    with _bootstrap_lock:
        _bootstrapped = False
