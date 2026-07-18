"""Bounded production retention for reminders, Activity, and the outbox."""

from __future__ import annotations

import asyncio
import dataclasses
import datetime as dt
import os
import tempfile
import unittest
from unittest import mock

import services.db as db
from app import cron
from services import retention
from services.config import settings as real_settings
from services.tenancy import tenant_context
from services.tenant_registry import TenantRecord


class RetentionTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._original_settings = db.settings
        db.settings = dataclasses.replace(
            real_settings,
            database_url="",
            sqlite_path=os.path.join(self._tmp.name, "retention.db"),
        )
        db.reset_bootstrap_state_for_tests()
        db.bootstrap()
        self.now = dt.datetime(2026, 7, 19, 12, 0, tzinfo=dt.timezone.utc)
        self.policy = retention.RetentionPolicy(
            dispatch_outbox_days=7,
            delivered_reminder_days=90,
            dismissed_activity_days=30,
            read_activity_days=90,
            tenant_batch_size=10,
            outbox_batch_size=10,
        )

    def tearDown(self):
        db.settings = self._original_settings
        db.reset_bootstrap_state_for_tests()
        self._tmp.cleanup()

    def _iso(self, *, days: int = 0) -> str:
        return (self.now + dt.timedelta(days=days)).isoformat()

    def _insert_reminder(
        self,
        reminder_id: str,
        *,
        tenant_id: str = "tenant-a",
        status: str = "delivered",
        due_days: int = -100,
        delivered_days: int | None = -100,
    ) -> None:
        with tenant_context(tenant_id), db.connect() as conn:
            conn.execute(
                """
                INSERT INTO reminders (
                    tenant_id, id, person_id, conversation_id, text, due_at,
                    timezone, source_surface, delivery_channel, chat_id, status,
                    created_at, delivered_at, last_error
                ) VALUES (?, ?, 'person-1', NULL, 'Reminder', ?, 'UTC',
                          'dashboard', 'dashboard', NULL, ?, ?, ?, NULL)
                """,
                (
                    tenant_id,
                    reminder_id,
                    self._iso(days=due_days),
                    status,
                    self._iso(days=-120),
                    (
                        self._iso(days=delivered_days)
                        if delivered_days is not None
                        else None
                    ),
                ),
            )

    def _insert_activity(
        self,
        item_id: str,
        *,
        tenant_id: str = "tenant-a",
        visible_days: int = -100,
        read_days: int | None = -100,
        dismissed_days: int | None = None,
    ) -> None:
        with tenant_context(tenant_id), db.connect() as conn:
            conn.execute(
                """
                INSERT INTO activity_items (
                    tenant_id, id, person_id, kind, title, body, source_id,
                    created_at, visible_at, read_at, dismissed_at
                ) VALUES (?, ?, 'person-1', 'reminder', 'Reminder', 'Body',
                          NULL, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    item_id,
                    self._iso(days=-120),
                    self._iso(days=visible_days),
                    self._iso(days=read_days) if read_days is not None else None,
                    (
                        self._iso(days=dismissed_days)
                        if dismissed_days is not None
                        else None
                    ),
                ),
            )

    def _insert_outbox(
        self,
        item_id: str,
        *,
        status: str = "delivered",
        created_days: int = -10,
        delivered_days: int | None = -10,
    ) -> None:
        with tenant_context("tenant-a"), db.connect() as conn:
            conn.execute(
                """
                INSERT INTO dispatch_outbox (
                    id, tenant_id, job_type, resource_id, payload_json, status,
                    created_at, available_at, delivered_at
                ) VALUES (?, 'tenant-a', 'reminder_due', ?, '{}', ?, ?, ?, ?)
                """,
                (
                    item_id,
                    item_id,
                    status,
                    self._iso(days=created_days),
                    self._iso(days=created_days),
                    (
                        self._iso(days=delivered_days)
                        if delivered_days is not None
                        else None
                    ),
                ),
            )

    def _ids(self, table: str) -> set[str]:
        with tenant_context("tenant-a"), db.connect() as conn:
            return {row["id"] for row in conn.execute(f"SELECT id FROM {table}")}

    def test_tenant_prune_deletes_only_old_delivered_past_reminders(self):
        self._insert_reminder("expired")
        self._insert_reminder("recent", delivered_days=-10)
        self._insert_reminder("pending", status="pending", delivered_days=None)
        self._insert_reminder("future", due_days=5)
        self._insert_reminder("other-tenant", tenant_id="tenant-b")

        with tenant_context("tenant-a"):
            result = retention.prune_tenant(policy=self.policy, now=self.now)

        self.assertEqual(result.reminders, 1)
        self.assertEqual(
            self._ids("reminders"),
            {"recent", "pending", "future", "other-tenant"},
        )

    def test_activity_prune_preserves_future_and_unread_items(self):
        self._insert_activity("old-read")
        self._insert_activity("old-dismissed", dismissed_days=-40)
        self._insert_activity("unread", read_days=None)
        self._insert_activity(
            "dismissed-unread",
            read_days=None,
            dismissed_days=-40,
        )
        self._insert_activity("future-read", visible_days=5)
        self._insert_activity("recent-read", read_days=-10)
        self._insert_activity(
            "recent-dismissed",
            read_days=-40,
            dismissed_days=-10,
        )

        with tenant_context("tenant-a"):
            result = retention.prune_tenant(policy=self.policy, now=self.now)

        self.assertEqual(result.dismissed_activity, 1)
        self.assertEqual(result.read_activity, 1)
        self.assertEqual(
            self._ids("activity_items"),
            {
                "unread",
                "dismissed-unread",
                "future-read",
                "recent-read",
                "recent-dismissed",
            },
        )

    def test_global_outbox_prune_is_status_timestamp_and_batch_bounded(self):
        self._insert_outbox("expired-1", created_days=-20, delivered_days=-20)
        self._insert_outbox("expired-2", created_days=-15, delivered_days=-15)
        self._insert_outbox("recent", created_days=-10, delivered_days=-2)
        self._insert_outbox("pending", status="pending", delivered_days=None)
        bounded = dataclasses.replace(self.policy, outbox_batch_size=1)

        first = retention.prune_global_outbox(policy=bounded, now=self.now)
        second = retention.prune_global_outbox(policy=bounded, now=self.now)

        self.assertEqual((first, second), (1, 1))
        self.assertEqual(self._ids("dispatch_outbox"), {"recent", "pending"})

    def test_tenant_batch_limit_is_applied_per_category(self):
        self._insert_reminder("expired-1")
        self._insert_reminder("expired-2")
        self._insert_activity("read-1")
        self._insert_activity("read-2")
        bounded = dataclasses.replace(self.policy, tenant_batch_size=1)

        with tenant_context("tenant-a"):
            result = retention.prune_tenant(policy=bounded, now=self.now)

        self.assertEqual(result.reminders, 1)
        self.assertEqual(result.read_activity, 1)
        self.assertEqual(len(self._ids("reminders")), 1)
        self.assertEqual(len(self._ids("activity_items")), 1)

    def test_policy_reads_config_and_rejects_unsafe_values(self):
        with mock.patch.dict(
            os.environ,
            {
                "RETENTION_DISPATCH_OUTBOX_DAYS": "14",
                "RETENTION_TENANT_BATCH_SIZE": "250",
            },
            clear=False,
        ):
            policy = retention.RetentionPolicy.from_env()
        self.assertEqual(policy.dispatch_outbox_days, 14)
        self.assertEqual(policy.tenant_batch_size, 250)

        with mock.patch.dict(
            os.environ,
            {"RETENTION_OUTBOX_BATCH_SIZE": "0"},
            clear=False,
        ), self.assertRaisesRegex(ValueError, "between 1 and"):
            retention.RetentionPolicy.from_env()

    def test_cron_prunes_global_outbox_once_and_fans_out_tenant_work(self):
        tenants = [
            TenantRecord("tenant-a", "A", "UTC", "active"),
            TenantRecord("tenant-b", "B", "UTC", "active"),
        ]
        with mock.patch.object(cron, "bootstrap"), mock.patch.object(
            cron.tenant_registry,
            "list_tenants",
            return_value=tenants,
        ), mock.patch.object(
            cron.retention,
            "prune_global_outbox",
            return_value=4,
        ) as global_prune, mock.patch.object(
            cron.queue,
            "enqueue",
        ) as enqueue:
            count = cron.fan_out("retention_cleanup")

        self.assertEqual(count, 2)
        global_prune.assert_called_once_with()
        self.assertEqual(enqueue.call_count, 2)

    def test_tenant_cron_handler_runs_in_tenant_context(self):
        observed: list[str] = []

        def capture():
            from services.tenancy import current_tenant_id

            observed.append(current_tenant_id())
            return retention.TenantRetentionResult("tenant-a", 1, 2, 3)

        with mock.patch.object(retention, "prune_tenant", side_effect=capture):
            asyncio.run(cron.run_job("retention_cleanup", "tenant-a"))

        self.assertEqual(observed, ["tenant-a"])


if __name__ == "__main__":
    unittest.main()
