"""
conversations.py — persistent chat threads, addressed by conversation id.

Every message the guardian and Cash exchange in the dashboard chat is stored in
the DB (``conversations`` + ``conversation_messages``), tenant-scoped, so the
transcript can be rebuilt for any conversation id and history survives restarts.

``send`` appends the user turn, runs the owner brain (via
``services.dashboard.chat_reply`` — shared memory + action execution), appends
Cash's reply, and titles the thread from its first message. Every query filters
by ``tenant_id`` explicitly (correct on SQLite and Postgres alike).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Optional

from services.db import connect
from services.tenancy import current_tenant_id, tenant_context


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


def _conv_row(row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"] or "New chat",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _msg_row(row) -> dict:
    return {
        "id": row["id"],
        "conversationId": row["conversation_id"],
        "role": row["role"],
        "content": row["content"],
        "action": row["action"],
        "createdAt": row["created_at"],
    }


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

def create_conversation(title: str = "") -> dict:
    tid = current_tenant_id()
    cid = _new_id("conv")
    now = _now_iso()
    with connect() as conn:
        conn.execute(
            "INSERT INTO conversations (tenant_id, id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (tid, cid, title or None, now, now),
        )
    return {"id": cid, "title": title or "New chat", "created_at": now, "updated_at": now}


def list_conversations(limit: int = 50) -> list[dict]:
    tid = current_tenant_id()
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM conversations WHERE tenant_id = ? ORDER BY updated_at DESC LIMIT ?",
            (tid, limit),
        ).fetchall()
    return [_conv_row(r) for r in rows]


def get_conversation(conversation_id: str) -> Optional[dict]:
    tid = current_tenant_id()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM conversations WHERE tenant_id = ? AND id = ?",
            (tid, conversation_id),
        ).fetchone()
    return _conv_row(row) if row else None


def rename_conversation(conversation_id: str, title: str) -> None:
    tid = current_tenant_id()
    with connect() as conn:
        conn.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE tenant_id = ? AND id = ?",
            (title, _now_iso(), tid, conversation_id),
        )


def delete_conversation(conversation_id: str) -> bool:
    tid = current_tenant_id()
    with connect() as conn:
        conn.execute(
            "DELETE FROM conversation_messages WHERE tenant_id = ? AND conversation_id = ?",
            (tid, conversation_id),
        )
        cur = conn.execute(
            "DELETE FROM conversations WHERE tenant_id = ? AND id = ?",
            (tid, conversation_id),
        )
    return bool(getattr(cur, "rowcount", 0))


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

def get_messages(conversation_id: str) -> list[dict]:
    tid = current_tenant_id()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM conversation_messages
             WHERE tenant_id = ? AND conversation_id = ?
             ORDER BY created_at ASC, id ASC
            """,
            (tid, conversation_id),
        ).fetchall()
    return [_msg_row(r) for r in rows]


def add_message(conversation_id: str, role: str, content: str, action: str = None) -> dict:
    tid = current_tenant_id()
    mid = _new_id("msg")
    now = _now_iso()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO conversation_messages
                (tenant_id, id, conversation_id, role, content, action, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (tid, mid, conversation_id, role, content, action, now),
        )
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE tenant_id = ? AND id = ?",
            (now, tid, conversation_id),
        )
    return {"id": mid, "conversationId": conversation_id, "role": role,
            "content": content, "action": action, "createdAt": now}


def _title_from(text: str) -> str:
    t = " ".join((text or "").split())
    return (t[:48] + "…") if len(t) > 48 else (t or "New chat")


def send(person_id: str, tenant_id: str, conversation_id: str, message: str, *, interpret=None) -> dict:
    """Append the user turn, run the brain, append Cash's reply. Returns
    ``{reply, action, userMessage, assistantMessage}``."""
    from services import dashboard
    message = (message or "").strip()
    with tenant_context(tenant_id):
        conv = get_conversation(conversation_id)
        if conv is None:
            raise ValueError("conversation not found")
        user_msg = add_message(conversation_id, "user", message)
        # Title an untitled thread from its first user message.
        if (conv.get("title") or "New chat") == "New chat":
            rename_conversation(conversation_id, _title_from(message))

        out = dashboard.chat_reply(person_id, tenant_id, message, interpret=interpret)
        reply = out.get("reply", "")
        action = out.get("action", "chat")
        assistant_msg = add_message(conversation_id, "assistant", reply, action=action)

    return {"reply": reply, "action": action,
            "userMessage": user_msg, "assistantMessage": assistant_msg}
