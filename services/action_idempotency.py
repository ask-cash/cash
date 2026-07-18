"""At-most-once guard for dashboard actions selected by a chat model.

Provider and worker retries are expected. A retry must never create a second
calendar event, reminder, or task after the first action reached an external
system. We persist intent before calling the action and cache the authoritative
result afterwards. If a process dies in between, the outcome is deliberately
reported as uncertain instead of repeating a potentially completed mutation.
"""

from __future__ import annotations

import datetime as dt
from typing import Callable, Optional

from services.db import connect
from services.tenancy import current_tenant_id

UNCERTAIN_RESULT = (
    "I couldn’t safely verify whether that action completed, so I did not repeat "
    "it. Check the destination before trying again."
)


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def run_once(
    conversation_id: str,
    request_id: str,
    action: str,
    execute: Callable[[], Optional[str]],
) -> Optional[str]:
    """Execute one action at most once for a canonical conversation request."""
    if not conversation_id or not request_id or action == "chat":
        return execute()

    tid = current_tenant_id()
    now = _now_iso()
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO chat_action_runs
                (tenant_id, conversation_id, request_id, action, status,
                 result_text, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'started', NULL, ?, ?)
            ON CONFLICT DO NOTHING
            """,
            (tid, conversation_id, request_id, action, now, now),
        )
        inserted = bool(getattr(cursor, "rowcount", 0))
        if not inserted:
            row = conn.execute(
                """
                SELECT action, status, result_text
                  FROM chat_action_runs
                 WHERE tenant_id = ? AND conversation_id = ?
                   AND request_id = ?
                """,
                (tid, conversation_id, request_id),
            ).fetchone()
            if row and row["status"] == "complete":
                return row["result_text"]
            return UNCERTAIN_RESULT

    try:
        result = execute()
    except Exception:
        # Keep the durable "started" marker. Repeating after an unknown failure
        # could duplicate an external side effect.
        raise

    with connect() as conn:
        conn.execute(
            """
            UPDATE chat_action_runs
               SET status = 'complete', result_text = ?, updated_at = ?
             WHERE tenant_id = ? AND conversation_id = ?
               AND request_id = ? AND action = ? AND status = 'started'
            """,
            (result, _now_iso(), tid, conversation_id, request_id, action),
        )
    return result
