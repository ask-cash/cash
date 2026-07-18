"""Durable, tenant-scoped inbox for the dashboard Activity page."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Optional

from services.db import connect
from services.tenancy import current_tenant_id


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _row_view(row) -> dict:
    return {
        "id": row["id"],
        "type": row["kind"],
        "title": row["title"],
        "text": row["body"],
        # The feed timestamp is when the item became relevant to the user, not
        # when a future reminder was originally scheduled.
        "createdAt": row["visible_at"],
        "readAt": row["read_at"],
    }


def publish(
    person_id: str,
    *,
    kind: str,
    title: str,
    text: str,
    source_id: str | None = None,
    created_at: str | None = None,
    visible_at: str | None = None,
    conn=None,
) -> dict:
    """Insert an inbox item and return it.

    ``source_id`` makes producer retries idempotent. When ``conn`` is supplied,
    the item participates in the caller's transaction.
    """
    person_id = (person_id or "").strip()
    if not person_id:
        raise ValueError("person_id is required")
    item_id = f"activity_{uuid.uuid4().hex[:20]}"
    tenant_id = current_tenant_id()
    created_at = created_at or _now_iso()
    visible_at = visible_at or created_at

    def _write(db):
        db.execute(
            """
            INSERT INTO activity_items
                (tenant_id, id, person_id, kind, title, body, source_id,
                 created_at, visible_at, read_at, dismissed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
            ON CONFLICT DO NOTHING
            """,
            (
                tenant_id,
                item_id,
                person_id,
                (kind or "update").strip()[:40],
                (title or "Cash update").strip()[:160],
                (text or "").strip()[:10_000],
                source_id or None,
                created_at,
                visible_at,
            ),
        )
        if source_id:
            return db.execute(
                "SELECT * FROM activity_items "
                "WHERE tenant_id = ? AND source_id = ?",
                (tenant_id, source_id),
            ).fetchone()
        return db.execute(
            "SELECT * FROM activity_items WHERE tenant_id = ? AND id = ?",
            (tenant_id, item_id),
        ).fetchone()

    if conn is not None:
        row = _write(conn)
    else:
        with connect() as db:
            row = _write(db)
    if row is None:  # pragma: no cover - defensive after insert
        raise RuntimeError("activity item could not be persisted")
    return _row_view(row)


def list_items(person_id: str, *, limit: int = 100) -> dict:
    tenant_id = current_tenant_id()
    limit = min(max(int(limit), 1), 200)
    now = _now_iso()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM activity_items
             WHERE tenant_id = ? AND person_id = ? AND dismissed_at IS NULL
               AND visible_at <= ?
             ORDER BY visible_at DESC, id DESC
             LIMIT ?
            """,
            (tenant_id, person_id, now, limit),
        ).fetchall()
        unread = conn.execute(
            """
            SELECT COUNT(*) AS count FROM activity_items
             WHERE tenant_id = ? AND person_id = ?
               AND dismissed_at IS NULL AND read_at IS NULL
               AND visible_at <= ?
            """,
            (tenant_id, person_id, now),
        ).fetchone()
    return {
        "items": [_row_view(row) for row in rows],
        "unreadCount": int(unread["count"] if unread else 0),
    }


def mark_read(person_id: str, item_id: str) -> Optional[dict]:
    tenant_id = current_tenant_id()
    now = _now_iso()
    with connect() as conn:
        conn.execute(
            """
            UPDATE activity_items
               SET read_at = COALESCE(read_at, ?)
             WHERE tenant_id = ? AND person_id = ? AND id = ?
               AND dismissed_at IS NULL AND visible_at <= ?
            """,
            (now, tenant_id, person_id, item_id, now),
        )
        row = conn.execute(
            "SELECT * FROM activity_items "
            "WHERE tenant_id = ? AND person_id = ? AND id = ? "
            "AND dismissed_at IS NULL AND visible_at <= ?",
            (tenant_id, person_id, item_id, now),
        ).fetchone()
    return _row_view(row) if row else None


def mark_all_read(person_id: str) -> int:
    tenant_id = current_tenant_id()
    now = _now_iso()
    with connect() as conn:
        cur = conn.execute(
            """
            UPDATE activity_items SET read_at = ?
             WHERE tenant_id = ? AND person_id = ?
               AND dismissed_at IS NULL AND read_at IS NULL
               AND visible_at <= ?
            """,
            (now, tenant_id, person_id, now),
        )
    return int(getattr(cur, "rowcount", 0) or 0)


def dismiss(person_id: str, item_id: str) -> bool:
    tenant_id = current_tenant_id()
    now = _now_iso()
    with connect() as conn:
        cur = conn.execute(
            """
            UPDATE activity_items SET dismissed_at = ?
             WHERE tenant_id = ? AND person_id = ? AND id = ?
               AND dismissed_at IS NULL AND visible_at <= ?
            """,
            (now, tenant_id, person_id, item_id, now),
        )
    return bool(getattr(cur, "rowcount", 0))


def clear(person_id: str) -> int:
    tenant_id = current_tenant_id()
    now = _now_iso()
    with connect() as conn:
        cur = conn.execute(
            """
            UPDATE activity_items SET dismissed_at = ?
             WHERE tenant_id = ? AND person_id = ? AND dismissed_at IS NULL
               AND visible_at <= ?
            """,
            (now, tenant_id, person_id, now),
        )
    return int(getattr(cur, "rowcount", 0) or 0)
