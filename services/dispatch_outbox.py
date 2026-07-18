"""Transactional, globally drainable queue-dispatch outbox.

Tenant data remains protected by RLS. This intentionally small control-plane
table is not RLS-scoped so one worker can recover committed work with a single
bounded query at high tenant counts.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Optional

from services.db import connect
from services.tenancy import current_tenant_id, system_context


def add(
    conn,
    *,
    dispatch_id: str,
    tenant_id: str,
    job_type: str,
    resource_id: str,
    payload: dict,
    created_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO dispatch_outbox
            (id, tenant_id, job_type, resource_id, payload_json, status,
             created_at, delivered_at)
        VALUES (?, ?, ?, ?, ?, 'pending', ?, NULL)
        ON CONFLICT(id) DO NOTHING
        """,
        (
            dispatch_id,
            tenant_id,
            job_type,
            resource_id,
            json.dumps(payload, separators=(",", ":")),
            created_at,
        ),
    )


def remove(
    conn,
    *,
    tenant_id: str,
    job_type: str,
    resource_id: str,
) -> None:
    conn.execute(
        "DELETE FROM dispatch_outbox "
        "WHERE tenant_id = ? AND job_type = ? AND resource_id = ?",
        (tenant_id, job_type, resource_id),
    )


def pending(limit: int = 200) -> list[dict]:
    limit = min(max(int(limit), 1), 1_000)
    with system_context():
        with connect() as conn:
            rows = conn.execute(
                """
                SELECT id, tenant_id, job_type, resource_id, payload_json,
                       created_at
                  FROM dispatch_outbox
                 WHERE status = 'pending'
                 ORDER BY created_at ASC, id ASC
                 LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [
        {
            "id": row["id"],
            "tenantId": row["tenant_id"],
            "jobType": row["job_type"],
            "resourceId": row["resource_id"],
            "payload": json.loads(row["payload_json"]),
            "createdAt": row["created_at"],
        }
        for row in rows
    ]


def pending_for_tenant(job_type: str, limit: int = 50) -> list[dict]:
    tenant_id = current_tenant_id()
    limit = min(max(int(limit), 1), 200)
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, resource_id, created_at
              FROM dispatch_outbox
             WHERE tenant_id = ? AND job_type = ? AND status = 'pending'
             ORDER BY created_at ASC, id ASC
             LIMIT ?
            """,
            (tenant_id, job_type, limit),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "resourceId": row["resource_id"],
            "createdAt": row["created_at"],
        }
        for row in rows
    ]


def mark_delivered(
    dispatch_id: str,
    delivered_at: Optional[str] = None,
) -> None:
    delivered_at = delivered_at or dt.datetime.now(dt.timezone.utc).isoformat()
    with system_context():
        with connect() as conn:
            conn.execute(
                "UPDATE dispatch_outbox "
                "SET status = 'delivered', delivered_at = ? "
                "WHERE id = ? AND status = 'pending'",
                (delivered_at, dispatch_id),
            )
