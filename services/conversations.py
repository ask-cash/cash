"""Persistent, tenant-scoped dashboard conversations and model context."""

from __future__ import annotations

import datetime as dt
import json
import re
import uuid
from typing import Optional

from services import attachments as attachment_store
from services import chat_policy
from services import dispatch_outbox
from services.chat_runtime import conversation_lock
from services.db import connect
from services.tenancy import current_tenant_id, tenant_context

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
_CHAT_JOB_TYPE = "chat_message"


class ChatJobDeferred(RuntimeError):
    """A later turn must yield until an earlier turn reaches a terminal state."""


class ChatJobTerminalError(RuntimeError):
    """A duplicate queue delivery refers to a job that already failed."""


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


def _has(row, column: str) -> bool:
    return row is not None and column in row.keys()


def _conv_row(row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"] or "New chat",
        "modelId": row["model_id"] if _has(row, "model_id") else None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _msg_row(row, attachments: list[dict] | None = None) -> dict:
    message = {
        "id": row["id"],
        "conversationId": row["conversation_id"],
        "role": row["role"],
        "content": row["content"],
        "action": row["action"],
        "createdAt": row["created_at"],
        "attachments": attachments or [],
    }
    if _has(row, "model_id") and row["model_id"]:
        message["modelId"] = row["model_id"]
    if _has(row, "input_tokens") or _has(row, "output_tokens"):
        message["usage"] = {
            "inputTokens": int(row["input_tokens"] or 0),
            "outputTokens": int(row["output_tokens"] or 0),
        }
    return message


def _clean_request_id(request_id: str | None) -> str:
    if not request_id:
        return f"req_{uuid.uuid4().hex}"
    request_id = request_id.strip()
    if not _REQUEST_ID_RE.match(request_id):
        raise chat_policy.ChatPolicyError(
            "Invalid client request id.",
            code="invalid_request_id",
        )
    return request_id


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

def create_conversation(title: str = "", model_id: str | None = None) -> dict:
    tid = current_tenant_id()
    cid = _new_id("conv")
    now = _now_iso()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO conversations
                (tenant_id, id, title, model_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (tid, cid, title or None, model_id, now, now),
        )
    return {
        "id": cid,
        "title": title or "New chat",
        "modelId": model_id,
        "created_at": now,
        "updated_at": now,
    }


def list_conversations(limit: int = 50) -> list[dict]:
    tid = current_tenant_id()
    limit = min(max(int(limit), 1), 100)
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM conversations WHERE tenant_id = ? "
            "ORDER BY updated_at DESC LIMIT ?",
            (tid, limit),
        ).fetchall()
    return [_conv_row(row) for row in rows]


def get_conversation(conversation_id: str) -> Optional[dict]:
    tid = current_tenant_id()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM conversations WHERE tenant_id = ? AND id = ?",
            (tid, conversation_id),
        ).fetchone()
    return _conv_row(row) if row else None


def rename_conversation(conversation_id: str, title: str) -> bool:
    tid = current_tenant_id()
    clean = " ".join((title or "").split())[:120] or "New chat"
    with connect() as conn:
        cur = conn.execute(
            "UPDATE conversations SET title = ?, updated_at = ? "
            "WHERE tenant_id = ? AND id = ?",
            (clean, _now_iso(), tid, conversation_id),
        )
    return bool(getattr(cur, "rowcount", 0))


def set_conversation_model(conversation_id: str, model_id: str) -> bool:
    tid = current_tenant_id()
    with connect() as conn:
        cur = conn.execute(
            "UPDATE conversations SET model_id = ?, updated_at = ? "
            "WHERE tenant_id = ? AND id = ?",
            (model_id, _now_iso(), tid, conversation_id),
        )
    return bool(getattr(cur, "rowcount", 0))


def delete_conversation(conversation_id: str) -> bool:
    tid = current_tenant_id()
    with conversation_lock(tid, conversation_id):
        if get_conversation(conversation_id) is None:
            return False
        if _has_active_job(conversation_id):
            raise chat_policy.ChatPolicyError(
                "Cash is still finishing a message in this conversation.",
                code="conversation_busy",
                status_code=409,
            )

        # The conversation lock is also used by send(), prepare_job(), media
        # creation, and individual attachment deletion. Once the active-job
        # check passes, no application path can claim or create another child
        # row while this cascade runs.
        attachment_store.delete_conversation_attachments(
            conversation_id,
            lock_held=True,
        )
        with connect() as conn:
            conn.execute(
                "DELETE FROM dispatch_outbox WHERE tenant_id = ? "
                "AND job_type = ? AND resource_id IN "
                "(SELECT id FROM chat_jobs WHERE tenant_id = ? "
                "AND conversation_id = ?)",
                (tid, _CHAT_JOB_TYPE, tid, conversation_id),
            )
            conn.execute(
                "DELETE FROM chat_outbox WHERE tenant_id = ? AND job_id IN "
                "(SELECT id FROM chat_jobs WHERE tenant_id = ? AND conversation_id = ?)",
                (tid, tid, conversation_id),
            )
            conn.execute(
                "DELETE FROM chat_action_runs WHERE tenant_id = ? AND conversation_id = ?",
                (tid, conversation_id),
            )
            conn.execute(
                "DELETE FROM chat_jobs WHERE tenant_id = ? AND conversation_id = ? "
                "AND status NOT IN ('pending', 'processing')",
                (tid, conversation_id),
            )
            conn.execute(
                "DELETE FROM conversation_messages WHERE tenant_id = ? AND conversation_id = ?",
                (tid, conversation_id),
            )
            cur = conn.execute(
                "DELETE FROM conversations WHERE tenant_id = ? AND id = ? "
                "AND NOT EXISTS ("
                "SELECT 1 FROM chat_jobs WHERE tenant_id = ? AND conversation_id = ? "
                "AND status IN ('pending', 'processing'))",
                (tid, conversation_id, tid, conversation_id),
            )
        if int(getattr(cur, "rowcount", 0) or 0) != 1:
            # Defensive fail-closed guard for a state transition outside the
            # normal locked service paths.
            raise chat_policy.ChatPolicyError(
                "Cash is still finishing a message in this conversation.",
                code="conversation_busy",
                status_code=409,
            )
        return True


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

def get_messages(
    conversation_id: str,
    *,
    limit: int = 200,
    include_private_attachments: bool = False,
) -> list[dict]:
    tid = current_tenant_id()
    limit = min(max(int(limit), 1), 500)
    with connect() as conn:
        # Select the most recent bounded page, then restore chronological order.
        rows = conn.execute(
            """
            SELECT * FROM (
                SELECT * FROM conversation_messages
                 WHERE tenant_id = ? AND conversation_id = ?
                 ORDER BY created_at DESC, id DESC
                 LIMIT ?
            ) recent
            ORDER BY created_at ASC, id ASC
            """,
            (tid, conversation_id, limit),
        ).fetchall()
        message_ids = [row["id"] for row in rows]
        if message_ids:
            placeholders = ",".join("?" for _ in message_ids)
            attachment_rows = conn.execute(
                f"""
                SELECT * FROM attachments
                 WHERE tenant_id = ? AND conversation_id = ?
                   AND message_id IN ({placeholders}) AND deleted_at IS NULL
                 ORDER BY created_at ASC, id ASC
                """,
                (tid, conversation_id, *message_ids),
            ).fetchall()
        else:
            attachment_rows = []

    grouped: dict[str, list[dict]] = {}
    for row in attachment_rows:
        grouped.setdefault(row["message_id"], []).append(
            attachment_store._row_view(  # internal DB projection, same tenant
                row,
                include_private=include_private_attachments,
            )
        )
    return [_msg_row(row, grouped.get(row["id"], [])) for row in rows]


def get_message(message_id: str, *, include_private_attachments: bool = False) -> Optional[dict]:
    tid = current_tenant_id()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM conversation_messages WHERE tenant_id = ? AND id = ?",
            (tid, message_id),
        ).fetchone()
    if row is None:
        return None
    attachments = []
    if row["role"] == "user":
        all_messages = get_messages(
            row["conversation_id"],
            include_private_attachments=include_private_attachments,
        )
        found = next((m for m in all_messages if m["id"] == message_id), None)
        if found:
            attachments = found["attachments"]
    return _msg_row(row, attachments)


def add_message(
    conversation_id: str,
    role: str,
    content: str,
    action: str | None = None,
    *,
    request_id: str | None = None,
    model_id: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> dict:
    if role not in {"user", "assistant"}:
        raise ValueError("invalid message role")
    tid = current_tenant_id()
    mid = _new_id("msg")
    now = _now_iso()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO conversation_messages
                (tenant_id, id, conversation_id, role, content, action,
                 request_id, model_id, input_tokens, output_tokens, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tid, mid, conversation_id, role, content or "", action,
                request_id, model_id, int(input_tokens or 0),
                int(output_tokens or 0), now,
            ),
        )
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE tenant_id = ? AND id = ?",
            (now, tid, conversation_id),
        )
    return {
        "id": mid,
        "conversationId": conversation_id,
        "role": role,
        "content": content or "",
        "action": action,
        "createdAt": now,
        "attachments": [],
        **({"modelId": model_id} if model_id else {}),
        "usage": {
            "inputTokens": int(input_tokens or 0),
            "outputTokens": int(output_tokens or 0),
        },
    }


def _delete_message(message_id: str) -> None:
    tid = current_tenant_id()
    attachment_store.unlink_from_message(message_id)
    with connect() as conn:
        conn.execute(
            "DELETE FROM conversation_messages WHERE tenant_id = ? AND id = ?",
            (tid, message_id),
        )


def _messages_for_request(conversation_id: str, request_id: str) -> tuple[dict | None, dict | None]:
    tid = current_tenant_id()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM conversation_messages
             WHERE tenant_id = ? AND conversation_id = ? AND request_id = ?
             ORDER BY created_at ASC, id ASC
            """,
            (tid, conversation_id, request_id),
        ).fetchall()
    user = next((_msg_row(row) for row in rows if row["role"] == "user"), None)
    assistant = next((_msg_row(row) for row in rows if row["role"] == "assistant"), None)
    if user:
        full = get_message(user["id"])
        user = full or user
    return user, assistant


def _title_from(text: str, records: list[dict]) -> str:
    value = " ".join((text or "").split())
    if not value and records:
        value = f"About {records[0].get('name') or 'attachment'}"
    return (value[:48] + "…") if len(value) > 48 else (value or "New chat")


def _record_usage(input_tokens: int, output_tokens: int) -> None:
    tid = current_tenant_id()
    now = _now_iso()
    usage_date = now[:10]
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO chat_usage
                (tenant_id, usage_date, request_count, input_tokens, output_tokens, updated_at)
            VALUES (?, ?, 1, ?, ?, ?)
            ON CONFLICT(tenant_id, usage_date) DO UPDATE SET
                request_count = chat_usage.request_count + 1,
                input_tokens = chat_usage.input_tokens + excluded.input_tokens,
                output_tokens = chat_usage.output_tokens + excluded.output_tokens,
                updated_at = excluded.updated_at
            """,
            (tid, usage_date, int(input_tokens or 0), int(output_tokens or 0), now),
        )


def conversation_context(conversation_id: str, plan: str, model_id: str) -> dict:
    messages = get_messages(conversation_id, include_private_attachments=True)
    return chat_policy.context_state(messages, plan, model_id).as_dict()


def send(
    person_id: str,
    tenant_id: str,
    conversation_id: str,
    message: str,
    *,
    plan: str = chat_policy.PLAN_FREE,
    model_id: str | None = None,
    attachment_ids: list[str] | None = None,
    client_request_id: str | None = None,
    interpret=None,
) -> dict:
    """Persist and process one ordered dashboard turn.

    Model and attachment authorization happen here, not in the browser. The
    client request id makes completed retries idempotent.
    """
    from services import dashboard

    text = (message or "").strip()
    attachment_ids = list(dict.fromkeys(attachment_ids or []))
    if not text and not attachment_ids:
        raise chat_policy.ChatPolicyError("Write a message or attach a file.", code="empty_message")
    request_id = _clean_request_id(client_request_id)
    plan = chat_policy.normalize_plan(plan)

    with tenant_context(tenant_id):
        with conversation_lock(tenant_id, conversation_id):
            conv = get_conversation(conversation_id)
            if conv is None:
                raise chat_policy.ChatPolicyError(
                    "Conversation not found.",
                    code="conversation_not_found",
                    status_code=404,
                )

            existing_user, existing_assistant = _messages_for_request(
                conversation_id,
                request_id,
            )
            if existing_user and existing_assistant:
                model = existing_assistant.get("modelId") or conv.get("modelId")
                return {
                    "reply": existing_assistant["content"],
                    "action": existing_assistant.get("action") or "chat",
                    "userMessage": existing_user,
                    "assistantMessage": existing_assistant,
                    "modelId": model,
                    "context": conversation_context(conversation_id, plan, model),
                    "idempotent": True,
                }
            if existing_user:
                raise chat_policy.ChatPolicyError(
                    "This message is already being processed.",
                    code="request_in_progress",
                    status_code=409,
                )

            requested_model = model_id or conv.get("modelId") or chat_policy.default_model_id(plan)
            model = chat_policy.require_model(plan, requested_model)
            if conv.get("modelId") != model.id:
                set_conversation_model(conversation_id, model.id)

            records = attachment_store.resolve_for_message(
                conversation_id,
                attachment_ids,
                plan=plan,
            )
            history = get_messages(
                conversation_id,
                include_private_attachments=True,
            )
            history_text, _ = chat_policy.assemble_history(
                history,
                limit_tokens=chat_policy.context_limit(plan, model),
                current_text=text,
                current_attachments=records,
            )

            user_message = add_message(
                conversation_id,
                "user",
                text,
                request_id=request_id,
                model_id=model.id,
            )
            try:
                attachment_store.link_to_message(attachment_ids, user_message["id"])
                out = dashboard.chat_reply(
                    person_id,
                    tenant_id,
                    text,
                    interpret=interpret,
                    conversation_history=history_text,
                    attachments=records,
                    model=model.id,
                    conversation_id=conversation_id,
                    request_id=request_id,
                )
            except Exception:
                _delete_message(user_message["id"])
                raise

            reply = (out.get("reply") or "").strip()
            action = out.get("action") or "chat"
            provider_usage = out.get("providerUsage") or {}
            input_tokens = int(provider_usage.get("inputTokens") or 0)
            output_tokens = int(provider_usage.get("outputTokens") or 0)
            assistant_message = add_message(
                conversation_id,
                "assistant",
                reply,
                action=action,
                request_id=request_id,
                model_id=model.id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            if (conv.get("title") or "New chat") == "New chat":
                rename_conversation(conversation_id, _title_from(text, records))
            _record_usage(input_tokens, output_tokens)

            # Reload the canonical user row now that attachments are linked.
            canonical_user = get_message(user_message["id"]) or user_message
            context = conversation_context(conversation_id, plan, model.id)

    return {
        "reply": reply,
        "action": action,
        "userMessage": canonical_user,
        "assistantMessage": assistant_message,
        "context": context,
        "modelId": model.id,
    }


# ---------------------------------------------------------------------------
# Durable chat job records (used when Redis-backed workers are enabled)
# ---------------------------------------------------------------------------

def create_job(
    person_id: str,
    conversation_id: str,
    user_message_id: str,
    request_id: str,
    model_id: str,
    plan: str,
) -> dict:
    tid = current_tenant_id()
    job_id = _new_id("chatjob")
    now = _now_iso()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO chat_jobs
                (tenant_id, id, conversation_id, person_id, user_message_id,
                 request_id, model_id, plan_id, status, result_json,
                 error_code, error_message, attempts, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', NULL, NULL, NULL, 0, ?, ?)
            """,
            (
                tid, job_id, conversation_id, person_id, user_message_id,
                request_id, model_id, plan, now, now,
            ),
        )
        _insert_outbox(conn, tid, job_id, now)
    return get_job(job_id)  # type: ignore[return-value]


def _insert_outbox(conn, tenant_id: str, job_id: str, now: str) -> None:
    dispatch_outbox.add(
        conn,
        dispatch_id=f"chat:{tenant_id}:{job_id}",
        tenant_id=tenant_id,
        job_type=_CHAT_JOB_TYPE,
        resource_id=job_id,
        payload={"job_id": job_id},
        created_at=now,
    )


def ensure_outbox(job_id: str) -> None:
    job = get_job(job_id)
    if not job or job.get("status") in {"complete", "failed"}:
        return
    tid = current_tenant_id()
    with connect() as conn:
        _insert_outbox(conn, tid, job_id, job["createdAt"])


def pending_outbox(limit: int = 50) -> list[dict]:
    tid = current_tenant_id()
    limit = min(max(int(limit), 1), 200)
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT o.resource_id, o.created_at
              FROM dispatch_outbox o
              JOIN chat_jobs j
                ON j.tenant_id = o.tenant_id
               AND j.id = o.resource_id
             WHERE o.tenant_id = ? AND o.job_type = ?
               AND o.status = 'pending'
               AND j.status IN ('pending', 'processing')
             ORDER BY o.created_at ASC, o.id ASC
             LIMIT ?
            """,
            (tid, _CHAT_JOB_TYPE, limit),
        ).fetchall()
    return [
        {"jobId": row["resource_id"], "createdAt": row["created_at"]}
        for row in rows
    ]


def mark_outbox_delivered(job_id: str) -> None:
    tid = current_tenant_id()
    dispatch_outbox.mark_delivered(
        f"chat:{tid}:{job_id}",
        _now_iso(),
    )


def _job_row(row) -> dict:
    result = json.loads(row["result_json"]) if row["result_json"] else None
    return {
        "id": row["id"],
        "conversationId": row["conversation_id"],
        "personId": row["person_id"],
        "userMessageId": row["user_message_id"],
        "requestId": row["request_id"],
        "modelId": row["model_id"],
        "planId": row["plan_id"],
        "status": row["status"],
        "result": result,
        "error": (
            {"code": row["error_code"], "message": row["error_message"]}
            if row["error_message"] else None
        ),
        "attempts": int(row["attempts"] or 0),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def get_job(job_id: str) -> Optional[dict]:
    tid = current_tenant_id()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM chat_jobs WHERE tenant_id = ? AND id = ?",
            (tid, job_id),
        ).fetchone()
    return _job_row(row) if row else None


def get_job_by_request(conversation_id: str, request_id: str) -> Optional[dict]:
    tid = current_tenant_id()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM chat_jobs WHERE tenant_id = ? AND conversation_id = ? "
            "AND request_id = ?",
            (tid, conversation_id, request_id),
        ).fetchone()
    return _job_row(row) if row else None


def _has_earlier_active_job(job: dict) -> bool:
    tid = current_tenant_id()
    with connect() as conn:
        row = conn.execute(
            """
            SELECT id
              FROM chat_jobs
             WHERE tenant_id = ? AND conversation_id = ? AND id <> ?
               AND status IN ('pending', 'processing')
               AND (
                    created_at < ?
                    OR (created_at = ? AND id < ?)
               )
             ORDER BY created_at ASC, id ASC
             LIMIT 1
            """,
            (
                tid,
                job["conversationId"],
                job["id"],
                job["createdAt"],
                job["createdAt"],
                job["id"],
            ),
        ).fetchone()
    return row is not None


def _has_active_job(conversation_id: str) -> bool:
    tid = current_tenant_id()
    with connect() as conn:
        row = conn.execute(
            "SELECT id FROM chat_jobs WHERE tenant_id = ? AND conversation_id = ? "
            "AND status IN ('pending', 'processing') LIMIT 1",
            (tid, conversation_id),
        ).fetchone()
    return row is not None


def _set_job(
    job_id: str,
    status: str,
    *,
    result: dict | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    increment_attempt: bool = False,
) -> None:
    tid = current_tenant_id()
    attempts_sql = ", attempts = attempts + 1" if increment_attempt else ""
    with connect() as conn:
        conn.execute(
            f"""
            UPDATE chat_jobs
               SET status = ?, result_json = ?, error_code = ?,
                   error_message = ?, updated_at = ?{attempts_sql}
             WHERE tenant_id = ? AND id = ?
            """,
            (
                status,
                json.dumps(result, ensure_ascii=False) if result is not None else None,
                error_code,
                error_message,
                _now_iso(),
                tid,
                job_id,
            ),
        )


def prepare_job(
    person_id: str,
    tenant_id: str,
    conversation_id: str,
    message: str,
    *,
    plan: str = chat_policy.PLAN_FREE,
    model_id: str | None = None,
    attachment_ids: list[str] | None = None,
    client_request_id: str | None = None,
) -> dict:
    """Atomically persist a user turn and durable pending job."""
    text = (message or "").strip()
    attachment_ids = list(dict.fromkeys(attachment_ids or []))
    if not text and not attachment_ids:
        raise chat_policy.ChatPolicyError("Write a message or attach a file.", code="empty_message")
    request_id = _clean_request_id(client_request_id)
    plan = chat_policy.normalize_plan(plan)

    with tenant_context(tenant_id):
        with conversation_lock(tenant_id, conversation_id):
            conv = get_conversation(conversation_id)
            if conv is None:
                raise chat_policy.ChatPolicyError(
                    "Conversation not found.",
                    code="conversation_not_found",
                    status_code=404,
                )

            existing_job = get_job_by_request(conversation_id, request_id)
            if existing_job:
                ensure_outbox(existing_job["id"])
                existing_job["_newlyCreated"] = False
                return existing_job
            existing_user, existing_assistant = _messages_for_request(
                conversation_id,
                request_id,
            )
            if existing_user and existing_assistant:
                chosen = (
                    existing_assistant.get("modelId")
                    or conv.get("modelId")
                    or chat_policy.default_model_id(plan)
                )
                result = {
                    "reply": existing_assistant["content"],
                    "action": existing_assistant.get("action") or "chat",
                    "userMessage": existing_user,
                    "assistantMessage": existing_assistant,
                    "modelId": chosen,
                    "context": conversation_context(conversation_id, plan, chosen),
                    "idempotent": True,
                }
                return {"status": "complete", "result": result, "requestId": request_id}
            if _has_active_job(conversation_id):
                raise chat_policy.ChatPolicyError(
                    "Cash is still finishing the previous message in this conversation.",
                    code="conversation_busy",
                    status_code=409,
                )

            requested_model = model_id or conv.get("modelId") or chat_policy.default_model_id(plan)
            model = chat_policy.require_model(plan, requested_model)

            # A gateway can stop after committing the user turn but before it
            # returns/enqueues the job. Reuse that canonical turn on a retry
            # instead of colliding with the request-id uniqueness constraint.
            if existing_user:
                now = _now_iso()
                job_id = _new_id("chatjob")
                tid = current_tenant_id()
                with connect() as conn:
                    conn.execute(
                        """
                        INSERT INTO chat_jobs
                            (tenant_id, id, conversation_id, person_id,
                             user_message_id, request_id, model_id, plan_id,
                             status, result_json, error_code, error_message,
                             attempts, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', NULL, NULL,
                                NULL, 0, ?, ?)
                        """,
                        (
                            tid, job_id, conversation_id, person_id,
                            existing_user["id"], request_id, model.id, plan,
                            now, now,
                        ),
                    )
                    _insert_outbox(conn, tid, job_id, now)
                    conn.execute(
                        "UPDATE conversations SET model_id = ?, updated_at = ? "
                        "WHERE tenant_id = ? AND id = ?",
                        (model.id, now, tid, conversation_id),
                    )
                job = get_job(job_id)
                if job is None:  # pragma: no cover
                    raise RuntimeError("chat job was not persisted")
                job["userMessage"] = existing_user
                job["context"] = conversation_context(
                    conversation_id,
                    plan,
                    model.id,
                )
                job["_newlyCreated"] = True
                return job

            records = attachment_store.resolve_for_message(
                conversation_id,
                attachment_ids,
                plan=plan,
            )
            history = get_messages(
                conversation_id,
                include_private_attachments=True,
            )
            # Reject an over-limit current turn before creating any durable rows.
            chat_policy.assemble_history(
                history,
                limit_tokens=chat_policy.context_limit(plan, model),
                current_text=text,
                current_attachments=records,
            )

            now = _now_iso()
            user_id = _new_id("msg")
            job_id = _new_id("chatjob")
            title = (
                _title_from(text, records)
                if (conv.get("title") or "New chat") == "New chat"
                else conv["title"]
            )
            tid = current_tenant_id()
            placeholders = ",".join("?" for _ in attachment_ids)
            with connect() as conn:
                conn.execute(
                    """
                    INSERT INTO conversation_messages
                        (tenant_id, id, conversation_id, role, content, action,
                         request_id, model_id, input_tokens, output_tokens, created_at)
                    VALUES (?, ?, ?, 'user', ?, NULL, ?, ?, 0, 0, ?)
                    """,
                    (tid, user_id, conversation_id, text, request_id, model.id, now),
                )
                if attachment_ids:
                    claimed = conn.execute(
                        f"UPDATE attachments SET message_id = ? WHERE tenant_id = ? "
                        f"AND conversation_id = ? AND id IN ({placeholders}) "
                        f"AND message_id IS NULL AND status = 'ready' AND deleted_at IS NULL",
                        (user_id, tid, conversation_id, *attachment_ids),
                    )
                    if int(getattr(claimed, "rowcount", 0) or 0) != len(attachment_ids):
                        raise attachment_store.AttachmentError(
                            "One or more attachments changed before they could be sent. "
                            "Review the draft and try again.",
                            code="attachment_claim_conflict",
                            status_code=409,
                        )
                conn.execute(
                    """
                    INSERT INTO chat_jobs
                        (tenant_id, id, conversation_id, person_id, user_message_id,
                         request_id, model_id, plan_id, status, result_json,
                         error_code, error_message, attempts, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', NULL, NULL, NULL, 0, ?, ?)
                    """,
                    (
                        tid, job_id, conversation_id, person_id, user_id,
                        request_id, model.id, plan, now, now,
                    ),
                )
                _insert_outbox(conn, tid, job_id, now)
                conn.execute(
                    "UPDATE conversations SET title = ?, model_id = ?, updated_at = ? "
                    "WHERE tenant_id = ? AND id = ?",
                    (title, model.id, now, tid, conversation_id),
                )

            job = get_job(job_id)
            if job is None:  # pragma: no cover
                raise RuntimeError("chat job was not persisted")
            job["userMessage"] = get_message(user_id)
            job["context"] = conversation_context(conversation_id, plan, model.id)
            job["_newlyCreated"] = True
            return job


def cancel_prepared_job(job_id: str) -> None:
    """Roll back a job that could not be placed on the durable queue."""
    job = get_job(job_id)
    if not job or job.get("status") != "pending":
        return
    tid = current_tenant_id()
    conversation_id = job["conversationId"]
    with conversation_lock(tid, conversation_id):
        # Re-read after acquiring the same lock as process_job(). A worker may
        # have claimed the job between the caller's initial read and this point.
        job = get_job(job_id)
        if not job or job.get("status") != "pending":
            return
        user_id = job["userMessageId"]
        user_message = get_message(user_id)
        conversation = get_conversation(conversation_id)
        generated_title = _title_from(
            (user_message or {}).get("content", ""),
            (user_message or {}).get("attachments") or [],
        )
        with connect() as conn:
            deleted = conn.execute(
                "DELETE FROM chat_jobs WHERE tenant_id = ? AND id = ? AND status = 'pending'",
                (tid, job_id),
            )
            if int(getattr(deleted, "rowcount", 0) or 0) != 1:
                return
            dispatch_outbox.remove(
                conn,
                tenant_id=tid,
                job_type=_CHAT_JOB_TYPE,
                resource_id=job_id,
            )
            conn.execute(
                "DELETE FROM chat_outbox WHERE tenant_id = ? AND job_id = ?",
                (tid, job_id),
            )
            conn.execute(
                "UPDATE attachments SET message_id = NULL "
                "WHERE tenant_id = ? AND message_id = ?",
                (tid, user_id),
            )
            conn.execute(
                "DELETE FROM conversation_messages WHERE tenant_id = ? AND id = ?",
                (tid, user_id),
            )
            remaining = conn.execute(
                "SELECT COUNT(*) AS count FROM conversation_messages "
                "WHERE tenant_id = ? AND conversation_id = ?",
                (tid, conversation_id),
            ).fetchone()
            if (
                int(remaining["count"] or 0) == 0
                and conversation
                and conversation.get("title") == generated_title
            ):
                conn.execute(
                    "UPDATE conversations SET title = NULL, updated_at = ? "
                    "WHERE tenant_id = ? AND id = ?",
                    (_now_iso(), tid, conversation_id),
                )


def process_job(tenant_id: str, job_id: str, *, interpret=None) -> dict:
    """Run one persisted chat job. Safe to call again after a worker retry."""
    from services import dashboard

    with tenant_context(tenant_id):
        initial = get_job(job_id)
        if initial is None:
            raise ValueError("chat job not found")
        # Receipt by a worker proves dispatch even when the gateway lost the
        # Redis response before it could settle the transactional outbox.
        mark_outbox_delivered(job_id)
        if initial["status"] == "complete" and initial.get("result"):
            return initial["result"]

        conversation_id = initial["conversationId"]
        with conversation_lock(tenant_id, conversation_id):
            job = get_job(job_id)
            if job is None:
                raise ValueError("chat job not found")
            if job["status"] == "complete" and job.get("result"):
                return job["result"]
            if job["status"] == "failed":
                raise ChatJobTerminalError(
                    (job.get("error") or {}).get("message")
                    or "This chat job has already failed."
                )
            if _has_earlier_active_job(job):
                raise ChatJobDeferred(
                    "An earlier message in this conversation is still processing."
                )

            existing_user, existing_assistant = _messages_for_request(
                conversation_id,
                job["requestId"],
            )
            if existing_assistant and existing_user:
                result = {
                    "reply": existing_assistant["content"],
                    "action": existing_assistant.get("action") or "chat",
                    "userMessage": existing_user,
                    "assistantMessage": existing_assistant,
                    "modelId": job["modelId"],
                    "context": conversation_context(
                        conversation_id,
                        job["planId"],
                        job["modelId"],
                    ),
                    "idempotent": True,
                }
                _set_job(job_id, "complete", result=result)
                return result
            if existing_user is None:
                raise ValueError("chat job user message is missing")

            _set_job(job_id, "processing", increment_attempt=True)
            user_message = get_message(
                job["userMessageId"],
                include_private_attachments=True,
            )
            if user_message is None:
                raise ValueError("chat job user message is missing")
            # Only earlier rows belong in this turn's context. A user can submit
            # several turns before workers pick them up; including every row
            # would leak a later question into an earlier model response.
            history = []
            for prior in get_messages(
                conversation_id,
                include_private_attachments=True,
            ):
                if prior["id"] == user_message["id"]:
                    break
                history.append(prior)
            model = chat_policy.require_model(job["planId"], job["modelId"])
            history_text, _ = chat_policy.assemble_history(
                history,
                limit_tokens=chat_policy.context_limit(job["planId"], model),
                current_text=user_message["content"],
                current_attachments=user_message.get("attachments") or [],
            )
            try:
                out = dashboard.chat_reply(
                    job["personId"],
                    tenant_id,
                    user_message["content"],
                    interpret=interpret,
                    conversation_history=history_text,
                    attachments=user_message.get("attachments") or [],
                    model=model.id,
                    conversation_id=conversation_id,
                    request_id=job["requestId"],
                )
                reply = (out.get("reply") or "").strip()
                action = out.get("action") or "chat"
                usage = out.get("providerUsage") or {}
                assistant_message = add_message(
                    conversation_id,
                    "assistant",
                    reply,
                    action=action,
                    request_id=job["requestId"],
                    model_id=model.id,
                    input_tokens=int(usage.get("inputTokens") or 0),
                    output_tokens=int(usage.get("outputTokens") or 0),
                )
                _record_usage(
                    int(usage.get("inputTokens") or 0),
                    int(usage.get("outputTokens") or 0),
                )
                canonical_user = get_message(user_message["id"]) or existing_user
                result = {
                    "reply": reply,
                    "action": action,
                    "userMessage": canonical_user,
                    "assistantMessage": assistant_message,
                    "modelId": model.id,
                    "context": conversation_context(
                        conversation_id,
                        job["planId"],
                        model.id,
                    ),
                }
                _set_job(job_id, "complete", result=result)
                return result
            except Exception:
                _set_job(job_id, "pending")
                raise


def fail_job(job_id: str, message: str = "") -> None:
    tid = current_tenant_id()
    with connect() as conn:
        conn.execute(
            """
            UPDATE chat_jobs
               SET status = 'failed', error_code = 'processing_failed',
                   error_message = ?, updated_at = ?
             WHERE tenant_id = ? AND id = ?
               AND status IN ('pending', 'processing')
            """,
            (
                message or "Cash could not complete this message after several attempts.",
                _now_iso(),
                tid,
                job_id,
            ),
        )
