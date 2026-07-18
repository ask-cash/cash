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
    "person_aliases",
    "directives",
    "person_summaries",
    "kv_documents",
    "event_log",
    "integration_connections",
    "conversations",
    "conversation_messages",
    "attachments",
    "chat_jobs",
    "chat_outbox",
    "chat_action_runs",
    "chat_usage",
    "reminders",
    "activity_items",
]

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id    TEXT PRIMARY KEY,
    display_name TEXT,
    email        TEXT,
    is_admin     INTEGER NOT NULL DEFAULT 0,
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

CREATE TABLE IF NOT EXISTS accounts (
    email         TEXT PRIMARY KEY,
    password_hash TEXT,
    first_name    TEXT,
    last_name     TEXT,
    tenant_id     TEXT NOT NULL,
    person_id     TEXT NOT NULL,
    role          TEXT,
    platforms     TEXT,
    onboarded     INTEGER NOT NULL DEFAULT 0,
    plan           TEXT NOT NULL DEFAULT 'free',
    auth_provider TEXT NOT NULL DEFAULT 'password',
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_accounts_person ON accounts(person_id);

CREATE TABLE IF NOT EXISTS integration_connections (
    tenant_id    TEXT NOT NULL DEFAULT 'default',
    provider_id  TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'connected',
    connected_at TEXT,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (tenant_id, provider_id)
);

CREATE TABLE IF NOT EXISTS conversations (
    tenant_id  TEXT NOT NULL DEFAULT 'default',
    id         TEXT PRIMARY KEY,
    title      TEXT,
    model_id   TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conversations_tenant_updated
    ON conversations(tenant_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS conversation_messages (
    tenant_id       TEXT NOT NULL DEFAULT 'default',
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    action          TEXT,
    request_id      TEXT,
    model_id        TEXT,
    input_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens   INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conv_msg ON conversation_messages(conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_conv_msg_tenant
    ON conversation_messages(tenant_id, conversation_id, created_at, id);

CREATE TABLE IF NOT EXISTS attachments (
    tenant_id       TEXT NOT NULL DEFAULT 'default',
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    message_id      TEXT,
    original_name   TEXT NOT NULL,
    storage_key     TEXT NOT NULL,
    mime_type       TEXT NOT NULL,
    size_bytes      INTEGER NOT NULL,
    checksum        TEXT NOT NULL,
    transcript      TEXT,
    status          TEXT NOT NULL DEFAULT 'ready',
    created_at      TEXT NOT NULL,
    deleted_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_attachments_conversation
    ON attachments(tenant_id, conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_attachments_message
    ON attachments(tenant_id, message_id);

CREATE TABLE IF NOT EXISTS chat_jobs (
    tenant_id       TEXT NOT NULL DEFAULT 'default',
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    person_id       TEXT NOT NULL,
    user_message_id TEXT NOT NULL,
    request_id      TEXT NOT NULL,
    model_id        TEXT NOT NULL,
    plan_id         TEXT NOT NULL DEFAULT 'free',
    status          TEXT NOT NULL DEFAULT 'pending',
    result_json     TEXT,
    error_code      TEXT,
    error_message   TEXT,
    attempts        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_jobs_request
    ON chat_jobs(tenant_id, conversation_id, request_id);
CREATE INDEX IF NOT EXISTS idx_chat_jobs_status
    ON chat_jobs(tenant_id, status, created_at);

CREATE TABLE IF NOT EXISTS chat_outbox (
    tenant_id   TEXT NOT NULL DEFAULT 'default',
    job_id      TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    created_at  TEXT NOT NULL,
    delivered_at TEXT,
    PRIMARY KEY (tenant_id, job_id)
);
CREATE INDEX IF NOT EXISTS idx_chat_outbox_pending
    ON chat_outbox(tenant_id, status, created_at);

-- Control-plane dispatch records deliberately have no RLS. Workers must be
-- able to recover committed queue work with one bounded query rather than
-- issuing a query per tenant.
CREATE TABLE IF NOT EXISTS dispatch_outbox (
    id            TEXT PRIMARY KEY,
    tenant_id     TEXT NOT NULL,
    job_type      TEXT NOT NULL,
    resource_id   TEXT NOT NULL,
    payload_json  TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',
    created_at    TEXT NOT NULL,
    -- Nullable for rolling upgrades: an older writer does not know this
    -- column and will omit it. Readers treat NULL as created_at (immediate).
    available_at  TEXT,
    delivered_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_dispatch_outbox_pending
    ON dispatch_outbox(status, created_at, id);
CREATE INDEX IF NOT EXISTS idx_dispatch_outbox_resource
    ON dispatch_outbox(tenant_id, job_type, resource_id);

CREATE TABLE IF NOT EXISTS chat_action_runs (
    tenant_id      TEXT NOT NULL DEFAULT 'default',
    conversation_id TEXT NOT NULL,
    request_id     TEXT NOT NULL,
    action         TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'started',
    result_text    TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    PRIMARY KEY (tenant_id, conversation_id, request_id, action)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_action_request
    ON chat_action_runs(tenant_id, conversation_id, request_id);

CREATE TABLE IF NOT EXISTS chat_usage (
    tenant_id     TEXT NOT NULL DEFAULT 'default',
    usage_date    TEXT NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0,
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    updated_at    TEXT NOT NULL,
    PRIMARY KEY (tenant_id, usage_date)
);

CREATE TABLE IF NOT EXISTS reminders (
    tenant_id       TEXT NOT NULL DEFAULT 'default',
    id              TEXT NOT NULL,
    person_id       TEXT,
    conversation_id TEXT,
    text            TEXT NOT NULL,
    due_at           TEXT NOT NULL,
    timezone         TEXT NOT NULL,
    source_surface   TEXT NOT NULL,
    delivery_channel TEXT NOT NULL,
    chat_id          TEXT,
    status           TEXT NOT NULL DEFAULT 'pending',
    created_at       TEXT NOT NULL,
    delivered_at     TEXT,
    last_error       TEXT,
    PRIMARY KEY (tenant_id, id)
);
CREATE INDEX IF NOT EXISTS idx_reminders_due
    ON reminders(tenant_id, status, due_at, id);

CREATE TABLE IF NOT EXISTS activity_items (
    tenant_id    TEXT NOT NULL DEFAULT 'default',
    id           TEXT NOT NULL,
    person_id    TEXT NOT NULL,
    kind         TEXT NOT NULL,
    title        TEXT NOT NULL,
    body         TEXT NOT NULL,
    source_id    TEXT,
    created_at   TEXT NOT NULL,
    visible_at   TEXT NOT NULL,
    read_at      TEXT,
    dismissed_at TEXT,
    PRIMARY KEY (tenant_id, id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_activity_source
    ON activity_items(tenant_id, source_id)
    WHERE source_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_activity_person
    ON activity_items(tenant_id, person_id, dismissed_at, created_at DESC, id);
CREATE INDEX IF NOT EXISTS idx_activity_visible
    ON activity_items(tenant_id, person_id, visible_at DESC, id)
    WHERE dismissed_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_activity_feed
    ON activity_items(
        tenant_id, person_id, dismissed_at, visible_at DESC, id
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

CREATE TABLE IF NOT EXISTS person_aliases (
    tenant_id           TEXT NOT NULL DEFAULT 'default',
    alias_person_id     TEXT NOT NULL,
    canonical_person_id TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    PRIMARY KEY (tenant_id, alias_person_id)
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
    email        TEXT,
    is_admin     BOOLEAN NOT NULL DEFAULT false,
    timezone     TEXT NOT NULL DEFAULT 'Asia/Kolkata',
    status       TEXT NOT NULL DEFAULT 'active',
    created_at   TEXT NOT NULL
);
-- Migrations for DBs created before email/is_admin existed (idempotent).
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS email TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT false;

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

CREATE TABLE IF NOT EXISTS accounts (
    email         TEXT PRIMARY KEY,
    password_hash TEXT,
    first_name    TEXT,
    last_name     TEXT,
    tenant_id     TEXT NOT NULL,
    person_id     TEXT NOT NULL,
    role          TEXT,
    platforms     TEXT,
    onboarded     BOOLEAN NOT NULL DEFAULT false,
    plan           TEXT NOT NULL DEFAULT 'free',
    auth_provider TEXT NOT NULL DEFAULT 'password',
    created_at    TEXT NOT NULL
);
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS plan TEXT NOT NULL DEFAULT 'free';
CREATE INDEX IF NOT EXISTS idx_accounts_person ON accounts(person_id);

CREATE TABLE IF NOT EXISTS integration_connections (
    tenant_id    TEXT NOT NULL DEFAULT current_setting('app.current_tenant', true),
    provider_id  TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'connected',
    connected_at TEXT,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (tenant_id, provider_id)
);

CREATE TABLE IF NOT EXISTS conversations (
    tenant_id  TEXT NOT NULL DEFAULT current_setting('app.current_tenant', true),
    id         TEXT PRIMARY KEY,
    title      TEXT,
    model_id   TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS model_id TEXT;
CREATE INDEX IF NOT EXISTS idx_conversations_tenant_updated
    ON conversations(tenant_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS conversation_messages (
    tenant_id       TEXT NOT NULL DEFAULT current_setting('app.current_tenant', true),
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    action          TEXT,
    request_id      TEXT,
    model_id        TEXT,
    input_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens   INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);
ALTER TABLE conversation_messages ADD COLUMN IF NOT EXISTS request_id TEXT;
ALTER TABLE conversation_messages ADD COLUMN IF NOT EXISTS model_id TEXT;
ALTER TABLE conversation_messages ADD COLUMN IF NOT EXISTS input_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE conversation_messages ADD COLUMN IF NOT EXISTS output_tokens INTEGER NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS idx_conv_msg ON conversation_messages(conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_conv_msg_tenant
    ON conversation_messages(tenant_id, conversation_id, created_at, id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_conv_msg_request
    ON conversation_messages(tenant_id, conversation_id, role, request_id)
    WHERE request_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS attachments (
    tenant_id       TEXT NOT NULL DEFAULT current_setting('app.current_tenant', true),
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    message_id      TEXT,
    original_name   TEXT NOT NULL,
    storage_key     TEXT NOT NULL,
    mime_type       TEXT NOT NULL,
    size_bytes      BIGINT NOT NULL,
    checksum        TEXT NOT NULL,
    transcript      TEXT,
    status          TEXT NOT NULL DEFAULT 'ready',
    created_at      TEXT NOT NULL,
    deleted_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_attachments_conversation
    ON attachments(tenant_id, conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_attachments_message
    ON attachments(tenant_id, message_id);

CREATE TABLE IF NOT EXISTS chat_jobs (
    tenant_id       TEXT NOT NULL DEFAULT current_setting('app.current_tenant', true),
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    person_id       TEXT NOT NULL,
    user_message_id TEXT NOT NULL,
    request_id      TEXT NOT NULL,
    model_id        TEXT NOT NULL,
    plan_id         TEXT NOT NULL DEFAULT 'free',
    status          TEXT NOT NULL DEFAULT 'pending',
    result_json     TEXT,
    error_code      TEXT,
    error_message   TEXT,
    attempts        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_jobs_request
    ON chat_jobs(tenant_id, conversation_id, request_id);
CREATE INDEX IF NOT EXISTS idx_chat_jobs_status
    ON chat_jobs(tenant_id, status, created_at);

CREATE TABLE IF NOT EXISTS chat_outbox (
    tenant_id    TEXT NOT NULL DEFAULT current_setting('app.current_tenant', true),
    job_id       TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    created_at   TEXT NOT NULL,
    delivered_at TEXT,
    PRIMARY KEY (tenant_id, job_id)
);
CREATE INDEX IF NOT EXISTS idx_chat_outbox_pending
    ON chat_outbox(tenant_id, status, created_at);

-- Control-plane dispatch records deliberately have no RLS. The application
-- only accesses this table through services.dispatch_outbox.
CREATE TABLE IF NOT EXISTS dispatch_outbox (
    id            TEXT PRIMARY KEY,
    tenant_id     TEXT NOT NULL,
    job_type      TEXT NOT NULL,
    resource_id   TEXT NOT NULL,
    payload_json  TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',
    created_at    TEXT NOT NULL,
    -- Nullable during the expand phase so old pods can keep inserting rows.
    available_at  TEXT,
    delivered_at TEXT
);
ALTER TABLE dispatch_outbox ADD COLUMN IF NOT EXISTS available_at TEXT;
-- Metadata-only repair for any environment that briefly received the earlier
-- contract-phase v3 schema. Old writers must be allowed to omit this column.
ALTER TABLE dispatch_outbox ALTER COLUMN available_at DROP NOT NULL;
CREATE INDEX IF NOT EXISTS idx_dispatch_outbox_pending
    ON dispatch_outbox(status, created_at, id);
CREATE INDEX IF NOT EXISTS idx_dispatch_outbox_resource
    ON dispatch_outbox(tenant_id, job_type, resource_id);

CREATE TABLE IF NOT EXISTS chat_action_runs (
    tenant_id       TEXT NOT NULL DEFAULT current_setting('app.current_tenant', true),
    conversation_id TEXT NOT NULL,
    request_id      TEXT NOT NULL,
    action          TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'started',
    result_text     TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    PRIMARY KEY (tenant_id, conversation_id, request_id, action)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_action_request
    ON chat_action_runs(tenant_id, conversation_id, request_id);

CREATE TABLE IF NOT EXISTS chat_usage (
    tenant_id     TEXT NOT NULL DEFAULT current_setting('app.current_tenant', true),
    usage_date    TEXT NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0,
    input_tokens  BIGINT NOT NULL DEFAULT 0,
    output_tokens BIGINT NOT NULL DEFAULT 0,
    updated_at    TEXT NOT NULL,
    PRIMARY KEY (tenant_id, usage_date)
);

CREATE TABLE IF NOT EXISTS reminders (
    tenant_id       TEXT NOT NULL DEFAULT current_setting('app.current_tenant', true),
    id              TEXT NOT NULL,
    person_id       TEXT,
    conversation_id TEXT,
    text            TEXT NOT NULL,
    due_at           TEXT NOT NULL,
    timezone         TEXT NOT NULL,
    source_surface   TEXT NOT NULL,
    delivery_channel TEXT NOT NULL,
    chat_id          TEXT,
    status           TEXT NOT NULL DEFAULT 'pending',
    created_at       TEXT NOT NULL,
    delivered_at     TEXT,
    last_error       TEXT,
    PRIMARY KEY (tenant_id, id)
);
CREATE INDEX IF NOT EXISTS idx_reminders_due
    ON reminders(tenant_id, status, due_at, id);

CREATE TABLE IF NOT EXISTS activity_items (
    tenant_id    TEXT NOT NULL DEFAULT current_setting('app.current_tenant', true),
    id           TEXT NOT NULL,
    person_id    TEXT NOT NULL,
    kind         TEXT NOT NULL,
    title        TEXT NOT NULL,
    body         TEXT NOT NULL,
    source_id    TEXT,
    created_at   TEXT NOT NULL,
    visible_at   TEXT NOT NULL,
    read_at      TEXT,
    dismissed_at TEXT,
    PRIMARY KEY (tenant_id, id)
);
ALTER TABLE activity_items ADD COLUMN IF NOT EXISTS visible_at TEXT;
UPDATE activity_items SET visible_at = created_at WHERE visible_at IS NULL;
ALTER TABLE activity_items ALTER COLUMN visible_at SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_activity_source
    ON activity_items(tenant_id, source_id)
    WHERE source_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_activity_person
    ON activity_items(tenant_id, person_id, dismissed_at, created_at DESC, id);
CREATE INDEX IF NOT EXISTS idx_activity_visible
    ON activity_items(tenant_id, person_id, visible_at DESC, id)
    WHERE dismissed_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_activity_feed
    ON activity_items(
        tenant_id, person_id, dismissed_at, visible_at DESC, id
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

CREATE TABLE IF NOT EXISTS person_aliases (
    tenant_id           TEXT NOT NULL DEFAULT current_setting('app.current_tenant', true),
    alias_person_id     TEXT NOT NULL,
    canonical_person_id TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    PRIMARY KEY (tenant_id, alias_person_id)
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


def _ensure_pg_rls(cur) -> None:
    """Create tenant RLS once without rewriting policies on every pod start."""
    for table in _TENANT_TABLES:
        cur.execute(
            """
            SELECT c.relrowsecurity, c.relforcerowsecurity
              FROM pg_class c
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = current_schema() AND c.relname = %s
            """,
            (table,),
        )
        flags = cur.fetchone()
        if not flags or not flags[0]:
            cur.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        if not flags or not flags[1]:
            # FORCE ensures the table owner is subject to the same policy.
            cur.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        cur.execute(
            """
            SELECT 1
              FROM pg_policies
             WHERE schemaname = current_schema()
               AND tablename = %s
               AND policyname = 'tenant_isolation'
            """,
            (table,),
        )
        if cur.fetchone() is None:
            cur.execute(
                f"CREATE POLICY tenant_isolation ON {table} "
                f"USING (tenant_id = current_setting('app.current_tenant', true)) "
                f"WITH CHECK (tenant_id = current_setting('app.current_tenant', true))"
            )


def _assert_pg_rls_role(cur) -> None:
    """Fail closed when the application role can bypass tenant policies.

    ``FORCE ROW LEVEL SECURITY`` subjects a normal table owner to RLS, but
    PostgreSQL superusers and roles carrying ``BYPASSRLS`` always bypass it.
    Running the web application with either attribute would turn an ordinary
    missing tenant predicate into a cross-tenant data exposure.
    """
    cur.execute(
        """
        SELECT rolsuper, rolbypassrls
          FROM pg_roles
         WHERE rolname = current_user
        """
    )
    flags = cur.fetchone()
    if flags is None:
        raise RuntimeError("Could not verify the PostgreSQL application role.")
    if bool(flags[0]) or bool(flags[1]):
        raise RuntimeError(
            "DATABASE_URL must use a PostgreSQL role with NOSUPERUSER and "
            "NOBYPASSRLS so tenant row-level security cannot be bypassed."
        )


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
            min_size=int(os.getenv("PG_POOL_MIN", "1")),
            max_size=int(os.getenv("PG_POOL_MAX", "5")),
            timeout=float(os.getenv("PG_POOL_TIMEOUT_SECONDS", "10")),
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
        _sqlite_add_missing_columns(conn, "tenants", {
            "email": "TEXT",
            "is_admin": "INTEGER NOT NULL DEFAULT 0",
        })
        _sqlite_add_missing_columns(conn, "accounts", {
            "plan": "TEXT NOT NULL DEFAULT 'free'",
        })
        _sqlite_add_missing_columns(conn, "conversations", {
            "model_id": "TEXT",
        })
        _sqlite_add_missing_columns(conn, "conversation_messages", {
            "request_id": "TEXT",
            "model_id": "TEXT",
            "input_tokens": "INTEGER NOT NULL DEFAULT 0",
            "output_tokens": "INTEGER NOT NULL DEFAULT 0",
        })
        _sqlite_add_missing_columns(conn, "dispatch_outbox", {
            "available_at": "TEXT",
        })
        _sqlite_add_missing_columns(conn, "activity_items", {
            "visible_at": "TEXT",
        })
        conn.execute(
            "UPDATE activity_items SET visible_at = created_at "
            "WHERE visible_at IS NULL"
        )
        # Backfill tenant_id on tables created before it existed, so every row is
        # attributable to a tenant and explicit tenant_id filters work on SQLite
        # (which has no RLS). New databases already have the column via the schema.
        for _t in ("people", "platform_identities", "directives", "person_summaries",
                   "person_aliases", "kv_documents", "event_log", "conversations",
                   "conversation_messages", "attachments", "chat_jobs", "chat_usage",
                   "reminders", "activity_items"):
            _sqlite_add_missing_columns(conn, _t, {
                "tenant_id": "TEXT NOT NULL DEFAULT 'default'",
            })
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_conv_msg_request
                ON conversation_messages(tenant_id, conversation_id, role, request_id)
                WHERE request_id IS NOT NULL
            """
        )
        conn.commit()
    finally:
        conn.close()
    logger.info("[db] SQLite schema ready at %s", settings.sqlite_path)


def _sqlite_add_missing_columns(conn, table: str, columns: dict[str, str]) -> None:
    """Idempotent ADD COLUMN for SQLite (no native IF NOT EXISTS).

    Reads the live column set via PRAGMA and adds only what's missing, so
    existing databases pick up new columns without a destructive rebuild.
    """
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, ddl in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
            logger.info("[db] migrated SQLite: added %s.%s", table, name)


# Arbitrary constant identifying the bootstrap DDL critical section. All roles
# use the same key so only one runs schema/RLS DDL at a time.
_BOOTSTRAP_LOCK_KEY = 911_002_001
# Bump whenever the forward-only Postgres schema or RLS set changes. The
# advisory lock plus this marker means one pod migrates while every other role
# performs only a cheap version read during a rollout.
_PG_SCHEMA_VERSION = "2026-07-19-reminders-activity-v4"


def _bootstrap_postgres() -> None:
    pool = _get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            _assert_pg_rls_role(cur)
            # Serialize bootstrap across processes. When several roles
            # (gateway/worker/connector/telegram) start at once, running the
            # RLS DDL (ALTER TABLE ... ENABLE RLS / CREATE POLICY on the same
            # tables) concurrently deadlocks. A transaction-scoped advisory lock
            # makes the others wait, then run the idempotent DDL as a no-op.
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (_BOOTSTRAP_LOCK_KEY,))
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS cash_schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute(
                "SELECT value FROM cash_schema_meta WHERE key = 'schema_version'"
            )
            version = cur.fetchone()
            if version is None or version[0] != _PG_SCHEMA_VERSION:
                for stmt in _split_statements(_PG_SCHEMA):
                    cur.execute(stmt)
                _ensure_pg_rls(cur)
                cur.execute(
                    """
                    INSERT INTO cash_schema_meta (key, value, updated_at)
                    VALUES ('schema_version', %s, now())
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                    """,
                    (_PG_SCHEMA_VERSION,),
                )
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
