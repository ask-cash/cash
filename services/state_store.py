"""
state_store.py — Tenant-scoped persistence for JSON documents and append-only
event logs, replacing the per-file user_data/*.json(l) blobs.

Two primitives cover everything the app stored on local disk:
  * documents  — a mutable JSON value addressed by (namespace, key).
                 Backs facts.json, decisions.json, tasks/<date>.json, files.json.
  * events     — an append-only ordered stream addressed by (namespace, key).
                 Backs conversations.jsonl and trading_journal.

Both are scoped to the active tenant (services.tenancy). In Postgres they live
in `kv_documents` / `event_log` under RLS; locally they fall back to files
under user_data/tenants/<tenant>/ so dev needs no infra.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from typing import Any, Optional

from services.db import connect, is_postgres
from services.tenancy import current_tenant_id


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

def read_json(namespace: str, key: str, default: Any = None) -> Any:
    if not is_postgres():
        return _file_read_json(namespace, key, default)
    with connect() as conn:
        row = conn.execute(
            "SELECT body FROM kv_documents WHERE tenant_id = ? AND namespace = ? AND doc_key = ?",
            (current_tenant_id(), namespace, key),
        ).fetchone()
    if row is None:
        return default
    return json.loads(row["body"])


def write_json(namespace: str, key: str, value: Any) -> None:
    if not is_postgres():
        _file_write_json(namespace, key, value)
        return
    body = json.dumps(value)
    now = _now_iso()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO kv_documents (tenant_id, namespace, doc_key, body, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (tenant_id, namespace, doc_key)
            DO UPDATE SET body = excluded.body, updated_at = excluded.updated_at
            """,
            (current_tenant_id(), namespace, key, body, now),
        )


# ---------------------------------------------------------------------------
# Append-only events
# ---------------------------------------------------------------------------

def append_event(namespace: str, key: str, entry: dict) -> None:
    if not is_postgres():
        _file_append_event(namespace, key, entry)
        return
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO event_log (tenant_id, namespace, log_key, body, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (current_tenant_id(), namespace, key, json.dumps(entry),
             entry.get("timestamp") or _now_iso()),
        )


def read_events(
    namespace: str,
    key: str,
    *,
    limit: Optional[int] = None,
) -> list[dict]:
    """Return events oldest-first. `limit` keeps only the most recent N."""
    if not is_postgres():
        rows = _file_read_events(namespace, key)
    else:
        with connect() as conn:
            results = conn.execute(
                """
                SELECT body FROM event_log
                 WHERE tenant_id = ? AND namespace = ? AND log_key = ?
                 ORDER BY id ASC
                """,
                (current_tenant_id(), namespace, key),
            ).fetchall()
        rows = [json.loads(r["body"]) for r in results]
    if limit is not None:
        return rows[-limit:]
    return rows


# ---------------------------------------------------------------------------
# Local-file fallback (dev / single-tenant). Scoped per tenant on disk.
# ---------------------------------------------------------------------------

def _tenant_dir(namespace: str) -> str:
    base = os.path.join("user_data", "tenants", current_tenant_id(), namespace)
    os.makedirs(base, exist_ok=True)
    return base


def _file_read_json(namespace: str, key: str, default: Any) -> Any:
    path = os.path.join(_tenant_dir(namespace), f"{key}.json")
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def _file_write_json(namespace: str, key: str, value: Any) -> None:
    path = os.path.join(_tenant_dir(namespace), f"{key}.json")
    with open(path, "w") as f:
        json.dump(value, f, indent=2)


def _file_append_event(namespace: str, key: str, entry: dict) -> None:
    path = os.path.join(_tenant_dir(namespace), f"{key}.jsonl")
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def _file_read_events(namespace: str, key: str) -> list[dict]:
    path = os.path.join(_tenant_dir(namespace), f"{key}.jsonl")
    if not os.path.exists(path):
        return []
    out: list[dict] = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out
