"""
store.py — SQLite primitives for Cash's identity / memory / behavior layer.

Single file at user_data/cash.db, WAL mode for concurrent readers across
processes (Telegram + Discord today; Slack + Teams later). Migrations are
forward-only and idempotent — every connection path runs ensure_schema().

The connect() context manager is the only entry point. It commits on clean
exit, rolls back on exception, and always closes.
"""

import datetime as dt
import logging
import os
import sqlite3
import threading
from contextlib import contextmanager

logger = logging.getLogger(__name__)

DB_PATH = os.path.join("user_data", "cash.db")


# ---------------------------------------------------------------------------
# Migrations — append new ones at the end. Forward-only.
# ---------------------------------------------------------------------------

MIGRATIONS: list[tuple[int, str, str]] = [
    (
        1,
        "0001_initial_identity",
        """
        CREATE TABLE IF NOT EXISTS people (
            person_id        TEXT PRIMARY KEY,
            canonical_name   TEXT,
            notes            TEXT,
            preferences_json TEXT,
            created_at       TEXT NOT NULL,
            updated_at       TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS platform_identities (
            platform_identity_id TEXT PRIMARY KEY,
            person_id            TEXT NOT NULL,
            platform             TEXT NOT NULL,
            workspace_id         TEXT NOT NULL DEFAULT '',
            platform_user_id     TEXT NOT NULL,
            display_name         TEXT,
            handle               TEXT,
            first_seen           TEXT NOT NULL,
            last_seen            TEXT NOT NULL,
            FOREIGN KEY(person_id) REFERENCES people(person_id),
            UNIQUE(platform, workspace_id, platform_user_id)
        );

        CREATE INDEX IF NOT EXISTS idx_pi_lookup
            ON platform_identities(platform, workspace_id, platform_user_id);
        CREATE INDEX IF NOT EXISTS idx_pi_person
            ON platform_identities(person_id);
        """,
    ),
    (
        2,
        "0002_directives",
        """
        CREATE TABLE IF NOT EXISTS directives (
            directive_id     TEXT PRIMARY KEY,
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
            FOREIGN KEY(target_person_id) REFERENCES people(person_id)
        );

        CREATE INDEX IF NOT EXISTS idx_dir_active
            ON directives(target_person_id, action, revoked_at, expires_at);
        CREATE INDEX IF NOT EXISTS idx_dir_scope
            ON directives(scope_platform, scope_workspace, scope_channel);
        """,
    ),
    (
        3,
        "0003_person_summaries",
        """
        CREATE TABLE IF NOT EXISTS person_summaries (
            person_id            TEXT PRIMARY KEY,
            summary_md           TEXT NOT NULL,
            last_built_at        TEXT NOT NULL,
            source_message_count INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(person_id) REFERENCES people(person_id)
        );
        """,
    ),
]


_schema_lock = threading.Lock()
_schema_ready = False


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Run any unapplied migrations. Idempotent — safe to call on every connection."""
    global _schema_ready

    if _schema_ready:
        return

    with _schema_lock:
        if _schema_ready:
            return

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version    INTEGER PRIMARY KEY,
                name       TEXT NOT NULL,
                applied_at TEXT NOT NULL
            );
            """
        )
        applied = {
            row[0]
            for row in conn.execute("SELECT version FROM schema_version").fetchall()
        }

        for version, name, sql in MIGRATIONS:
            if version in applied:
                continue
            logger.info("[identity.store] applying migration %s (%s)", version, name)
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_version(version, name, applied_at) VALUES (?, ?, ?)",
                (version, name, _now_iso()),
            )
        conn.commit()
        _schema_ready = True


@contextmanager
def connect():
    """Yield a sqlite3 connection. Commits on clean exit, rolls back on exception.

    WAL mode and foreign keys are enabled. Schema migrations run on first call
    in this process; subsequent calls skip via the _schema_ready flag.
    """
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        ensure_schema(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def reset_schema_state_for_tests() -> None:
    """Test-only: clear the once-per-process schema-ready flag."""
    global _schema_ready
    with _schema_lock:
        _schema_ready = False
