"""
test_notifications.py — proactive-message decision engine (Feature 5).

Covers the routing/suppression policy (never talk over an active turn; urgent
signals always go through; routing hint > preferred channel > default), the
activity clock, and dispatch to queue-backed connectors vs in-process Telegram.
Stdlib unittest with an in-memory state_store fake and a stub outbound queue.

Run:  ./venv/bin/python -m unittest tests.test_notifications -v
"""

import datetime as dt
import unittest

from services import notifications


class _FakeStore:
    def __init__(self):
        self.json = {}

    def read_json(self, ns, key, default=None):
        return self.json.get((ns, key), default)

    def write_json(self, ns, key, value):
        self.json[(ns, key)] = value


class _StubQueue:
    def __init__(self):
        self.enqueued = []

    def enqueue_outbound(self, platform, tenant_id, payload):
        self.enqueued.append((platform, tenant_id, payload))


class _NotifBase(unittest.TestCase):
    def setUp(self):
        self.store = _FakeStore()
        self.queue = _StubQueue()
        self._orig_store = notifications.state_store
        self._orig_queue = notifications.queue
        self._orig_tenant = notifications.current_tenant_id
        self._orig_now = notifications._now
        notifications.state_store = self.store
        notifications.queue = self.queue
        notifications.current_tenant_id = lambda: "tnt_test"
        self._clock = dt.datetime(2026, 7, 11, 12, 0, 0)
        notifications._now = lambda: self._clock

    def tearDown(self):
        notifications.state_store = self._orig_store
        notifications.queue = self._orig_queue
        notifications.current_tenant_id = self._orig_tenant
        notifications._now = self._orig_now

    def _advance(self, seconds):
        self._clock = self._clock + dt.timedelta(seconds=seconds)


class DecidePolicyTest(_NotifBase):
    def test_suppresses_heartbeat_during_active_conversation(self):
        d = notifications.decide(
            notifications.Signal(notifications.KIND_HEARTBEAT, "psst"), active=True)
        self.assertEqual(d.outcome, notifications.SUPPRESS)
        self.assertFalse(d.should_deliver)

    def test_delivers_heartbeat_when_quiet(self):
        d = notifications.decide(
            notifications.Signal(notifications.KIND_HEARTBEAT, "psst"), active=False)
        self.assertEqual(d.outcome, notifications.DELIVER)
        self.assertFalse(d.reuse)

    def test_urgent_kind_delivers_even_when_active(self):
        # Reminders are not in the suppressible set -> urgent -> always delivered.
        d = notifications.decide(
            notifications.Signal(notifications.KIND_REMINDER, "5pm!"), active=True)
        self.assertEqual(d.outcome, notifications.DELIVER)
        self.assertTrue(d.reuse)  # threads into the open conversation

    def test_routing_urgent_flag_overrides_suppression(self):
        d = notifications.decide(
            notifications.Signal(notifications.KIND_HEARTBEAT, "psst", {"urgent": True}),
            active=True)
        self.assertEqual(d.outcome, notifications.DELIVER)

    def test_routing_hint_beats_preferred_channel(self):
        notifications.set_preferred_channel("discord")
        d = notifications.decide(
            notifications.Signal(notifications.KIND_HEARTBEAT, "hi", {"channel": "slack"}),
            active=False)
        self.assertEqual(d.channel, "slack")

    def test_preferred_channel_used_without_hint(self):
        notifications.set_preferred_channel("discord")
        d = notifications.decide(
            notifications.Signal(notifications.KIND_HEARTBEAT, "hi"), active=False)
        self.assertEqual(d.channel, "discord")

    def test_defaults_to_telegram(self):
        d = notifications.decide(
            notifications.Signal(notifications.KIND_HEARTBEAT, "hi"), active=False)
        self.assertEqual(d.channel, "telegram")


class ActivityClockTest(_NotifBase):
    def test_touch_makes_conversation_active(self):
        self.assertFalse(notifications.is_conversation_active("telegram"))
        notifications.touch_activity("telegram")
        self.assertTrue(notifications.is_conversation_active("telegram"))

    def test_active_window_expires(self):
        notifications.touch_activity("telegram")
        self._advance(notifications.ACTIVE_WINDOW_SECONDS + 1)
        self.assertFalse(notifications.is_conversation_active("telegram"))

    def test_activity_is_per_channel(self):
        notifications.touch_activity("telegram")
        self.assertTrue(notifications.is_conversation_active("telegram"))
        self.assertFalse(notifications.is_conversation_active("discord"))

    def test_no_activity_is_not_active(self):
        self.assertIsNone(notifications.seconds_since_last_activity("telegram"))
        self.assertFalse(notifications.is_conversation_active())


class EmitDispatchTest(_NotifBase):
    def test_queue_backed_channel_enqueues_outbound(self):
        notifications.set_preferred_channel("discord")
        d = notifications.emit_signal(notifications.KIND_HEARTBEAT, "hello")
        self.assertTrue(d.should_deliver)
        self.assertTrue(d.dispatched)
        self.assertEqual(len(self.queue.enqueued), 1)
        platform, tenant, payload = self.queue.enqueued[0]
        self.assertEqual(platform, "discord")
        self.assertEqual(tenant, "tnt_test")
        self.assertEqual(payload["text"], "hello")
        self.assertEqual(payload["to"], "owner")
        self.assertIn("idempotency_key", payload)

    def test_telegram_channel_does_not_enqueue(self):
        # Telegram is delivered in-process by the caller, not via the queue.
        d = notifications.emit_signal(notifications.KIND_HEARTBEAT, "hello")
        self.assertEqual(d.channel, "telegram")
        self.assertTrue(d.should_deliver)
        self.assertFalse(d.dispatched)
        self.assertEqual(self.queue.enqueued, [])

    def test_suppressed_signal_does_not_dispatch(self):
        notifications.set_preferred_channel("discord")
        notifications.touch_activity("discord")
        d = notifications.emit_signal(notifications.KIND_HEARTBEAT, "hello")
        self.assertEqual(d.outcome, notifications.SUPPRESS)
        self.assertFalse(d.dispatched)
        self.assertEqual(self.queue.enqueued, [])


class PreferredChannelTest(_NotifBase):
    def test_set_and_get_roundtrip(self):
        self.assertEqual(notifications.get_preferred_channel(), "telegram")
        notifications.set_preferred_channel("Discord")
        self.assertEqual(notifications.get_preferred_channel(), "discord")

    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            notifications.set_preferred_channel("")


if __name__ == "__main__":
    unittest.main()
