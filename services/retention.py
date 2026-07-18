"""Bounded retention for reminder, Activity, and dispatch-outbox records.

Tenant-owned rows are pruned only while a tenant context is active, preserving
PostgreSQL RLS as the final isolation boundary. The global dispatch outbox is
pruned separately in system context so a scheduled run performs one bounded
control-plane query, rather than one global scan for every tenant.

All retention windows and batch sizes have conservative production defaults.
Invalid configuration fails the maintenance job without affecting request or
worker startup.
"""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass

from services.db import connect
from services.tenancy import current_tenant_id, system_context

_UTC = dt.timezone.utc
_MAX_RETENTION_DAYS = 3_650
_MAX_BATCH_SIZE = 5_000


def _configured_int(
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a whole number") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


@dataclass(frozen=True)
class RetentionPolicy:
    """Retention windows and hard per-invocation delete caps."""

    dispatch_outbox_days: int = 7
    delivered_reminder_days: int = 90
    dismissed_activity_days: int = 30
    read_activity_days: int = 90
    tenant_batch_size: int = 500
    outbox_batch_size: int = 1_000

    @classmethod
    def from_env(cls) -> RetentionPolicy:
        return cls(
            dispatch_outbox_days=_configured_int(
                "RETENTION_DISPATCH_OUTBOX_DAYS",
                cls.dispatch_outbox_days,
                minimum=1,
                maximum=_MAX_RETENTION_DAYS,
            ),
            delivered_reminder_days=_configured_int(
                "RETENTION_DELIVERED_REMINDER_DAYS",
                cls.delivered_reminder_days,
                minimum=1,
                maximum=_MAX_RETENTION_DAYS,
            ),
            dismissed_activity_days=_configured_int(
                "RETENTION_DISMISSED_ACTIVITY_DAYS",
                cls.dismissed_activity_days,
                minimum=1,
                maximum=_MAX_RETENTION_DAYS,
            ),
            read_activity_days=_configured_int(
                "RETENTION_READ_ACTIVITY_DAYS",
                cls.read_activity_days,
                minimum=1,
                maximum=_MAX_RETENTION_DAYS,
            ),
            tenant_batch_size=_configured_int(
                "RETENTION_TENANT_BATCH_SIZE",
                cls.tenant_batch_size,
                minimum=1,
                maximum=_MAX_BATCH_SIZE,
            ),
            outbox_batch_size=_configured_int(
                "RETENTION_OUTBOX_BATCH_SIZE",
                cls.outbox_batch_size,
                minimum=1,
                maximum=_MAX_BATCH_SIZE,
            ),
        )


@dataclass(frozen=True)
class TenantRetentionResult:
    tenant_id: str
    reminders: int
    dismissed_activity: int
    read_activity: int

    @property
    def total(self) -> int:
        return self.reminders + self.dismissed_activity + self.read_activity


def _utc_now(now: dt.datetime | None) -> dt.datetime:
    value = now or dt.datetime.now(_UTC)
    if value.tzinfo is None:
        raise ValueError("retention time must include a timezone")
    return value.astimezone(_UTC)


def _cutoff(now: dt.datetime, days: int) -> str:
    return (now - dt.timedelta(days=days)).isoformat()


def _rowcount(cursor) -> int:
    return max(int(getattr(cursor, "rowcount", 0) or 0), 0)


def prune_tenant(
    *,
    policy: RetentionPolicy | None = None,
    now: dt.datetime | None = None,
) -> TenantRetentionResult:
    """Delete a bounded set of expired rows for the current tenant.

    Future Activity and reminders are protected explicitly. Activity must also
    have ``read_at`` set; a dismissed-but-unread item remains durable.
    """

    policy = policy or RetentionPolicy.from_env()
    now_utc = _utc_now(now)
    now_iso = now_utc.isoformat()
    tenant_id = current_tenant_id()
    reminder_cutoff = _cutoff(now_utc, policy.delivered_reminder_days)
    dismissed_cutoff = _cutoff(now_utc, policy.dismissed_activity_days)
    read_cutoff = _cutoff(now_utc, policy.read_activity_days)

    with connect() as conn:
        reminder_cursor = conn.execute(
            """
            DELETE FROM reminders
             WHERE tenant_id = ? AND id IN (
                SELECT id FROM reminders
                 WHERE tenant_id = ?
                   AND status = 'delivered'
                   AND delivered_at IS NOT NULL
                   AND delivered_at <= ?
                   AND due_at <= ?
                 ORDER BY delivered_at ASC, id ASC
                 LIMIT ?
             )
            """,
            (
                tenant_id,
                tenant_id,
                reminder_cutoff,
                now_iso,
                policy.tenant_batch_size,
            ),
        )
        dismissed_cursor = conn.execute(
            """
            DELETE FROM activity_items
             WHERE tenant_id = ? AND id IN (
                SELECT id FROM activity_items
                 WHERE tenant_id = ?
                   AND visible_at <= ?
                   AND read_at IS NOT NULL
                   AND dismissed_at IS NOT NULL
                   AND dismissed_at <= ?
                 ORDER BY dismissed_at ASC, id ASC
                 LIMIT ?
             )
            """,
            (
                tenant_id,
                tenant_id,
                now_iso,
                dismissed_cutoff,
                policy.tenant_batch_size,
            ),
        )
        read_cursor = conn.execute(
            """
            DELETE FROM activity_items
             WHERE tenant_id = ? AND id IN (
                SELECT id FROM activity_items
                 WHERE tenant_id = ?
                   AND visible_at <= ?
                   AND read_at IS NOT NULL
                   AND read_at <= ?
                   AND dismissed_at IS NULL
                 ORDER BY read_at ASC, id ASC
                 LIMIT ?
             )
            """,
            (
                tenant_id,
                tenant_id,
                now_iso,
                read_cutoff,
                policy.tenant_batch_size,
            ),
        )

    return TenantRetentionResult(
        tenant_id=tenant_id,
        reminders=_rowcount(reminder_cursor),
        dismissed_activity=_rowcount(dismissed_cursor),
        read_activity=_rowcount(read_cursor),
    )


def prune_global_outbox(
    *,
    policy: RetentionPolicy | None = None,
    now: dt.datetime | None = None,
) -> int:
    """Delete one bounded batch of delivered global outbox records.

    ``created_at`` is included in the predicate and ordering so the existing
    ``(status, created_at, id)`` index can bound candidate discovery. No schema
    or startup migration is required.
    """

    policy = policy or RetentionPolicy.from_env()
    now_utc = _utc_now(now)
    cutoff = _cutoff(now_utc, policy.dispatch_outbox_days)
    with system_context():
        with connect() as conn:
            cursor = conn.execute(
                """
                DELETE FROM dispatch_outbox
                 WHERE id IN (
                    SELECT id FROM dispatch_outbox
                     WHERE status = 'delivered'
                       AND delivered_at IS NOT NULL
                       AND delivered_at <= ?
                       AND created_at <= ?
                     ORDER BY created_at ASC, id ASC
                     LIMIT ?
                 )
                """,
                (cutoff, cutoff, policy.outbox_batch_size),
            )
    return _rowcount(cursor)
