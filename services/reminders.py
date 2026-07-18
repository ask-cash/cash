"""Durable, tenant-scoped one-off reminders.

Dashboard reminders are written to three records in one database transaction:
the reminder, a future-dated Activity item, and a delayed dispatch-outbox row.
The Activity item is the guaranteed delivery path: it becomes visible at
``due_at`` even if Redis or every worker is temporarily unavailable. The
outbox job performs secondary delivery bookkeeping and can project to a
genuinely connected external surface later without weakening that guarantee.

Telegram-created reminders intentionally retain the legacy tenant document
store plus python-telegram-bot JobQueue. Keeping that path stable preserves
already-scheduled reminders during the dashboard scheduler rollout. Dashboard
records written by the previous implementation are identifiable by
``chat_id=0`` and are migrated idempotently into Activity when that user first
loads the feed.
"""

from __future__ import annotations

import datetime as dt
import uuid
from zoneinfo import ZoneInfo

from services import activity
from services import dispatch_outbox
from services import state_store
from services.db import connect
from services.tenancy import current_tenant_id
from services.user_profile import now as _profile_now

_REMINDER_JOB_TYPE = "reminder_due"
_UTC = dt.timezone.utc
NAMESPACE = "reminders"
KEY = "pending"


def _now_utc() -> dt.datetime:
    return dt.datetime.now(_UTC)


def _utc_iso(value: dt.datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("reminder time must include a timezone")
    return value.astimezone(_UTC).isoformat()


def _row_view(row) -> dict:
    return {
        "id": row["id"],
        "text": row["text"],
        # ``when`` and integer ``chat_id`` preserve the Telegram handler API.
        "when": row["due_at"],
        "dueAt": row["due_at"],
        "timezone": row["timezone"],
        "chat_id": int(row["chat_id"]) if str(row["chat_id"] or "").isdigit() else 0,
        "tenant_id": row["tenant_id"],
        "personId": row["person_id"],
        "conversationId": row["conversation_id"],
        "sourceSurface": row["source_surface"],
        "deliveryChannel": row["delivery_channel"],
        "status": row["status"],
        "created": row["created_at"],
        "deliveredAt": row["delivered_at"],
    }


def add(text: str, when_iso: str, chat_id: int) -> dict:
    """Persist a Telegram reminder using the established compatibility store."""
    rec = {
        "id": uuid.uuid4().hex,
        "text": text,
        "when": when_iso,
        "chat_id": chat_id,
        "tenant_id": current_tenant_id(),
        "created": _profile_now().isoformat(),
    }
    items = state_store.read_json(NAMESPACE, KEY, default=[]) or []
    items.append(rec)
    state_store.write_json(NAMESPACE, KEY, items)
    return rec


def add_dashboard(
    text: str,
    when: dt.datetime,
    *,
    person_id: str,
    conversation_id: str,
    timezone: str,
) -> dict:
    """Persist one dashboard reminder and its future Activity item."""
    return add_dashboard_batch(
        [{"text": text, "when": when}],
        person_id=person_id,
        conversation_id=conversation_id,
        timezone=timezone,
    )[0]


def add_dashboard_batch(
    items: list[dict],
    *,
    person_id: str,
    conversation_id: str,
    timezone: str,
) -> list[dict]:
    """Persist a validated reminder batch atomically.

    A database error rolls back every reminder, future Activity item, and due
    outbox entry in the batch; callers never receive a partial success.
    """
    if not items:
        raise ValueError("at least one reminder is required")
    if not person_id:
        raise ValueError("person_id is required for dashboard reminders")
    timezone_name = ZoneInfo(timezone).key
    tenant_id = current_tenant_id()
    created_at = _now_utc().isoformat()
    prepared: list[dict] = []
    for item in items:
        clean_text = (item.get("text") or "").strip()
        when = item.get("when")
        if not clean_text:
            raise ValueError("reminder text is required")
        if not isinstance(when, dt.datetime):
            raise ValueError("reminder time is required")
        requested_id = str(item.get("_id") or "").strip()
        if len(requested_id) > 128:
            raise ValueError("reminder id is too long")
        prepared.append(
            {
                # ``_id`` is reserved for the one-time legacy dashboard
                # migration. Normal reminder creation always generates a new
                # opaque id.
                "id": requested_id or uuid.uuid4().hex,
                "text": clean_text,
                "due_at": _utc_iso(when),
            }
        )

    with connect() as conn:
        for reminder in prepared:
            reminder_id = reminder["id"]
            conn.execute(
                """
                INSERT INTO reminders
                    (tenant_id, id, person_id, conversation_id, text, due_at,
                     timezone, source_surface, delivery_channel, chat_id, status,
                     created_at, delivered_at, last_error)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'dashboard', 'dashboard', NULL,
                        'pending', ?, NULL, NULL)
                ON CONFLICT(tenant_id, id) DO NOTHING
                """,
                (
                    tenant_id,
                    reminder_id,
                    person_id,
                    conversation_id or None,
                    reminder["text"],
                    reminder["due_at"],
                    timezone_name,
                    created_at,
                ),
            )
            activity.publish(
                person_id,
                kind="reminder",
                title="Reminder",
                text=reminder["text"],
                source_id=f"reminder:{reminder_id}",
                created_at=created_at,
                visible_at=reminder["due_at"],
                conn=conn,
            )
            dispatch_outbox.add(
                conn,
                dispatch_id=f"reminder:{tenant_id}:{reminder_id}",
                tenant_id=tenant_id,
                job_type=_REMINDER_JOB_TYPE,
                resource_id=reminder_id,
                payload={"reminder_id": reminder_id},
                created_at=created_at,
                available_at=reminder["due_at"],
            )
    return [
        record
        for reminder in prepared
        if (record := get_dashboard(reminder["id"])) is not None
    ]


def get_dashboard(reminder_id: str) -> dict | None:
    tenant_id = current_tenant_id()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM reminders WHERE tenant_id = ? AND id = ?",
            (tenant_id, reminder_id),
        ).fetchone()
    return _row_view(row) if row else None


def remove(reminder_id: str) -> None:
    """Delete a Telegram reminder from the compatibility store."""
    items = state_store.read_json(NAMESPACE, KEY, default=[]) or []
    state_store.write_json(
        NAMESPACE,
        KEY,
        [item for item in items if item.get("id") != reminder_id],
    )


def list_pending() -> list[dict]:
    """Telegram reminders, including overdue rows for poller recovery.

    ``chat_id=0`` was the old dashboard placeholder, not a deliverable Telegram
    destination. Excluding it prevents the poller from firing and deleting a
    dashboard reminder before the Activity compatibility migration sees it.
    """
    items = state_store.read_json(NAMESPACE, KEY, default=[]) or []
    return sorted(
        [
            reminder
            for reminder in items
            if str(reminder.get("chat_id", "")).strip() != "0"
        ],
        key=lambda reminder: reminder.get("when", ""),
    )


def migrate_legacy_dashboard(
    person_id: str,
    *,
    timezone: str | None = None,
) -> int:
    """Move pre-Activity dashboard reminders into the durable inbox.

    The old dashboard wrote reminders to the Telegram document store with the
    sentinel ``chat_id=0``. The original random id is mapped to a deterministic
    new id, making retries safe if the process commits the new rows and exits
    before it can remove the legacy document entry. Malformed legacy records
    remain untouched for manual recovery.
    """
    person_id = (person_id or "").strip()
    if not person_id:
        raise ValueError("person_id is required")

    if not timezone:
        from services.user_profile import load_profile

        timezone = load_profile().get("timezone") or "Asia/Kolkata"
    timezone_name = ZoneInfo(timezone).key
    zone = ZoneInfo(timezone_name)
    tenant_id = current_tenant_id()
    legacy_items = state_store.read_json(NAMESPACE, KEY, default=[]) or []
    prepared: list[dict] = []
    migrated_legacy_ids: set[str] = set()

    for record in legacy_items:
        if not isinstance(record, dict):
            continue
        if str(record.get("chat_id", "")).strip() != "0":
            continue
        legacy_id = str(record.get("id") or "").strip()
        text = str(record.get("text") or "").strip()
        if not legacy_id or not text:
            continue
        try:
            when = dt.datetime.fromisoformat(str(record.get("when") or ""))
        except (TypeError, ValueError):
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=zone)
        deterministic_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"cash://{tenant_id}/legacy-dashboard-reminder/{legacy_id}",
        ).hex
        prepared.append({"_id": deterministic_id, "text": text, "when": when})
        migrated_legacy_ids.add(legacy_id)

    if not prepared:
        return 0

    add_dashboard_batch(
        prepared,
        person_id=person_id,
        conversation_id="",
        timezone=timezone_name,
    )

    # Re-read after committing so a concurrent legacy writer is less likely to
    # be overwritten. Remove only the exact dashboard ids just migrated and
    # preserve every Telegram reminder and any newly-added document record.
    current_items = state_store.read_json(NAMESPACE, KEY, default=[]) or []
    state_store.write_json(
        NAMESPACE,
        KEY,
        [
            record
            for record in current_items
            if not (
                isinstance(record, dict)
                and str(record.get("chat_id", "")).strip() == "0"
                and str(record.get("id") or "").strip() in migrated_legacy_ids
            )
        ],
    )
    return len(migrated_legacy_ids)


def list_dashboard_pending(person_id: str) -> list[dict]:
    """Pending dashboard reminders belonging to one authenticated person."""
    if not person_id:
        raise ValueError("person_id is required")
    tenant_id = current_tenant_id()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM reminders
             WHERE tenant_id = ? AND person_id = ? AND status = 'pending'
             ORDER BY due_at ASC, id ASC
            """,
            (tenant_id, person_id),
        ).fetchall()
    return [_row_view(row) for row in rows]


def complete_dashboard_delivery(reminder_id: str) -> dict | None:
    """Idempotently mark a due dashboard reminder complete.

    The Activity item already committed with the reminder and becomes visible
    based on its UTC ``visible_at`` timestamp, so this job is bookkeeping rather
    than the sole delivery path.
    """
    tenant_id = current_tenant_id()
    now = _now_utc().isoformat()
    with connect() as conn:
        conn.execute(
            """
            UPDATE reminders
               SET status = 'delivered', delivered_at = COALESCE(delivered_at, ?),
                   last_error = NULL
             WHERE tenant_id = ? AND id = ? AND source_surface = 'dashboard'
               AND status = 'pending'
            """,
            (now, tenant_id, reminder_id),
        )
        row = conn.execute(
            "SELECT * FROM reminders WHERE tenant_id = ? AND id = ?",
            (tenant_id, reminder_id),
        ).fetchone()
    return _row_view(row) if row else None
