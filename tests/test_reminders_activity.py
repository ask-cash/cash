"""Dashboard reminder scheduling and durable Activity delivery."""

from __future__ import annotations

import dataclasses
import datetime as dt
import asyncio
import os
import tempfile
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

import services.db as db
from services import activity, dispatch_outbox, reminders
from services.config import settings as _real_settings
from services.tenancy import tenant_context


class ReminderActivityTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        path = os.path.join(self._tmp.name, "reminders.db")
        self._orig_settings = db.settings
        db.settings = dataclasses.replace(
            _real_settings,
            database_url="",
            sqlite_path=path,
        )
        db.reset_bootstrap_state_for_tests()
        self.clock = dt.datetime(2026, 7, 19, 0, 0, tzinfo=dt.timezone.utc)

    def tearDown(self):
        db.settings = self._orig_settings
        db.reset_bootstrap_state_for_tests()
        self._tmp.cleanup()

    def _schedule(self, *, minutes: int = 2, person_id: str = "pers_1"):
        due = self.clock + dt.timedelta(minutes=minutes)
        with tenant_context("tenant-1"), mock.patch.object(
            reminders,
            "_now_utc",
            return_value=self.clock,
        ):
            record = reminders.add_dashboard(
                "Drink water",
                due.astimezone(ZoneInfo("Asia/Kolkata")),
                person_id=person_id,
                conversation_id="conv_1",
                timezone="Asia/Kolkata",
            )
        return record, due

    def test_schedule_atomically_creates_future_activity_and_due_outbox(self):
        record, due = self._schedule()

        with tenant_context("tenant-1"):
            with mock.patch.object(activity, "_now_iso", return_value=self.clock.isoformat()):
                self.assertEqual(activity.list_items("pers_1"), {"items": [], "unreadCount": 0})

            with db.connect() as conn:
                item = conn.execute(
                    "SELECT source_id, created_at, visible_at FROM activity_items "
                    "WHERE tenant_id = ?",
                    ("tenant-1",),
                ).fetchone()
                outbox = conn.execute(
                    "SELECT created_at, available_at FROM dispatch_outbox "
                    "WHERE tenant_id = ? AND resource_id = ?",
                    ("tenant-1", record["id"]),
                ).fetchone()

        self.assertEqual(item["source_id"], f"reminder:{record['id']}")
        self.assertEqual(item["created_at"], self.clock.isoformat())
        self.assertEqual(item["visible_at"], due.isoformat())
        self.assertEqual(outbox["created_at"], self.clock.isoformat())
        self.assertEqual(outbox["available_at"], due.isoformat())

    def test_utc_conversion_from_user_timezone(self):
        record, due = self._schedule()
        self.assertEqual(record["dueAt"], due.isoformat())
        self.assertEqual(record["timezone"], "Asia/Kolkata")

    def test_outbox_does_not_publish_before_available_at(self):
        record, due = self._schedule()
        with mock.patch.object(
            dispatch_outbox,
            "_now_iso",
            return_value=self.clock.isoformat(),
        ):
            self.assertEqual(dispatch_outbox.pending(), [])
        with mock.patch.object(
            dispatch_outbox,
            "_now_iso",
            return_value=(due + dt.timedelta(seconds=1)).isoformat(),
        ):
            pending = dispatch_outbox.pending()
        self.assertEqual([item["resourceId"] for item in pending], [record["id"]])

    def test_activity_becomes_visible_at_due_time_without_worker(self):
        _, due = self._schedule()
        after_due = (due + dt.timedelta(seconds=1)).isoformat()

        with tenant_context("tenant-1"), mock.patch.object(
            activity,
            "_now_iso",
            return_value=after_due,
        ):
            feed = activity.list_items("pers_1")

        self.assertEqual(feed["unreadCount"], 1)
        self.assertEqual(len(feed["items"]), 1)
        self.assertEqual(feed["items"][0]["type"], "reminder")
        self.assertEqual(feed["items"][0]["text"], "Drink water")
        self.assertEqual(feed["items"][0]["createdAt"], due.isoformat())

    def test_clear_and_read_all_cannot_consume_future_reminders(self):
        _, due = self._schedule(minutes=10)
        before_due = self.clock.isoformat()
        after_due = (due + dt.timedelta(seconds=1)).isoformat()

        with tenant_context("tenant-1"), mock.patch.object(
            activity,
            "_now_iso",
            return_value=before_due,
        ):
            self.assertEqual(activity.mark_all_read("pers_1"), 0)
            self.assertEqual(activity.clear("pers_1"), 0)

        with tenant_context("tenant-1"), mock.patch.object(
            activity,
            "_now_iso",
            return_value=after_due,
        ):
            feed = activity.list_items("pers_1")
        self.assertEqual(feed["unreadCount"], 1)
        self.assertEqual(len(feed["items"]), 1)

    def test_worker_bookkeeping_is_idempotent(self):
        from app import worker

        record, due = self._schedule()
        after_due = due + dt.timedelta(seconds=1)

        with tenant_context("tenant-1"), mock.patch.object(
            reminders,
            "_now_utc",
            return_value=after_due,
        ):
            asyncio.run(
                worker._handle_reminder_due(
                    "tenant-1",
                    {"reminder_id": record["id"]},
                )
            )
            first = reminders.get_dashboard(record["id"])
            asyncio.run(
                worker._handle_reminder_due(
                    "tenant-1",
                    {"reminder_id": record["id"]},
                )
            )
            second = reminders.get_dashboard(record["id"])

        self.assertEqual(first["status"], "delivered")
        self.assertEqual(second["status"], "delivered")
        self.assertEqual(first["deliveredAt"], second["deliveredAt"])

    def test_clock_skew_after_due_enqueue_cannot_leave_reminder_pending(self):
        record, due = self._schedule()
        # The outbox gate is authoritative. Simulate a worker whose wall clock
        # is behind the scheduler that already released this due job.
        worker_clock = due - dt.timedelta(seconds=30)
        with tenant_context("tenant-1"), mock.patch.object(
            reminders,
            "_now_utc",
            return_value=worker_clock,
        ):
            settled = reminders.complete_dashboard_delivery(record["id"])
        self.assertEqual(settled["status"], "delivered")

    def test_multi_reminder_database_failure_rolls_back_whole_batch(self):
        due = self.clock + dt.timedelta(minutes=2)
        original_publish = activity.publish
        calls = 0

        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("simulated database failure")
            return original_publish(*args, **kwargs)

        with tenant_context("tenant-1"), mock.patch.object(
            reminders,
            "_now_utc",
            return_value=self.clock,
        ), mock.patch.object(
            activity,
            "publish",
            side_effect=fail_second,
        ), self.assertRaises(RuntimeError):
            reminders.add_dashboard_batch(
                [
                    {"text": "First", "when": due},
                    {"text": "Second", "when": due + dt.timedelta(minutes=1)},
                ],
                person_id="pers_1",
                conversation_id="conv_1",
                timezone="UTC",
            )

        with tenant_context("tenant-1"), db.connect() as conn:
            reminder_count = conn.execute(
                "SELECT COUNT(*) FROM reminders WHERE tenant_id = ?",
                ("tenant-1",),
            ).fetchone()[0]
            activity_count = conn.execute(
                "SELECT COUNT(*) FROM activity_items WHERE tenant_id = ?",
                ("tenant-1",),
            ).fetchone()[0]
            outbox_count = conn.execute(
                "SELECT COUNT(*) FROM dispatch_outbox WHERE tenant_id = ?",
                ("tenant-1",),
            ).fetchone()[0]
        self.assertEqual((reminder_count, activity_count, outbox_count), (0, 0, 0))

    def test_activity_is_person_and_tenant_scoped(self):
        self._schedule(person_id="pers_1")
        after_due = (self.clock + dt.timedelta(minutes=3)).isoformat()

        with tenant_context("tenant-1"), mock.patch.object(
            activity,
            "_now_iso",
            return_value=after_due,
        ):
            self.assertEqual(activity.list_items("pers_other")["items"], [])
        with tenant_context("tenant-2"), mock.patch.object(
            activity,
            "_now_iso",
            return_value=after_due,
        ):
            self.assertEqual(activity.list_items("pers_1")["items"], [])

    def test_pending_reminders_are_person_scoped_within_one_tenant(self):
        first, _ = self._schedule(person_id="pers_1")
        second, _ = self._schedule(person_id="pers_2")

        with tenant_context("tenant-1"):
            person_one = reminders.list_dashboard_pending("pers_1")
            person_two = reminders.list_dashboard_pending("pers_2")

        self.assertEqual([item["id"] for item in person_one], [first["id"]])
        self.assertEqual([item["id"] for item in person_two], [second["id"]])

    def test_legacy_dashboard_reminder_migrates_to_activity_idempotently(self):
        legacy_due = self.clock - dt.timedelta(minutes=5)
        legacy = {
            "id": "legacy-dashboard-1",
            "text": "Drink water",
            # The previous dashboard implementation stored a naive local time.
            "when": legacy_due.astimezone(ZoneInfo("Asia/Kolkata"))
            .replace(tzinfo=None)
            .isoformat(),
            "chat_id": 0,
            "tenant_id": "tenant-1",
            "created": (self.clock - dt.timedelta(minutes=10)).isoformat(),
        }
        telegram = {
            **legacy,
            "id": "telegram-1",
            "chat_id": 12345,
            "text": "Telegram reminder",
        }
        with tenant_context("tenant-1"):
            from services import state_store

            state_store.write_json(
                reminders.NAMESPACE,
                reminders.KEY,
                [legacy, telegram],
            )
            first = reminders.migrate_legacy_dashboard(
                "pers_1",
                timezone="Asia/Kolkata",
            )
            second = reminders.migrate_legacy_dashboard(
                "pers_1",
                timezone="Asia/Kolkata",
            )
            with mock.patch.object(
                activity,
                "_now_iso",
                return_value=self.clock.isoformat(),
            ):
                feed = activity.list_items("pers_1")
            remaining = state_store.read_json(
                reminders.NAMESPACE,
                reminders.KEY,
                default=[],
            )
            state_store.write_json(reminders.NAMESPACE, reminders.KEY, [])

        self.assertEqual((first, second), (1, 0))
        self.assertEqual(len(feed["items"]), 1)
        self.assertEqual(feed["items"][0]["text"], "Drink water")
        self.assertEqual(feed["items"][0]["createdAt"], legacy_due.isoformat())
        self.assertEqual([item["id"] for item in remaining], ["telegram-1"])

    def test_telegram_pending_excludes_legacy_dashboard_sentinel(self):
        with tenant_context("tenant-1"):
            from services import state_store

            state_store.write_json(
                reminders.NAMESPACE,
                reminders.KEY,
                [
                    {
                        "id": "dashboard",
                        "text": "Dashboard",
                        "when": "2099-07-19T06:00:00",
                        "chat_id": 0,
                    },
                    {
                        "id": "telegram",
                        "text": "Telegram",
                        "when": "2099-07-19T06:00:00+05:30",
                        "chat_id": -100123,
                    },
                ],
            )
            pending = reminders.list_pending()
            state_store.write_json(reminders.NAMESPACE, reminders.KEY, [])

        self.assertEqual([item["id"] for item in pending], ["telegram"])

    def test_telegram_compatibility_store_is_unchanged(self):
        when = "2026-07-19T06:00:00+05:30"
        with tenant_context("tenant-1"), mock.patch.object(
            reminders,
            "_profile_now",
            return_value=self.clock.astimezone(ZoneInfo("Asia/Kolkata")),
        ):
            record = reminders.add("Legacy reminder", when, 12345)
            self.assertEqual(reminders.list_pending(), [record])
            reminders.remove(record["id"])
            self.assertEqual(reminders.list_pending(), [])


if __name__ == "__main__":
    unittest.main()
