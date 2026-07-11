"""
test_proactivity.py — Heartbeat, follow-ups, task rollover (Feature 3).

Covers: heartbeat stays quiet when nothing's due and never calls the LLM at boot;
it speaks when the guardian is slipping (via an injected LLM); follow-ups surface
only when overdue and resolve on completion; tasks carry priority tiers and a
stable, visible rollover age. Stdlib unittest with an in-memory state_store fake.

Run:  ./venv/bin/python -m unittest tests.test_proactivity -v
"""

import datetime as dt
import unittest

from services import (
    followups,
    heartbeat,
    memory,
    persona,
    task_tracker,
    user_profile,
)


class _FakeStore:
    def __init__(self):
        self.json = {}
        self.events = {}

    def read_json(self, ns, key, default=None):
        return self.json.get((ns, key), default)

    def write_json(self, ns, key, value):
        self.json[(ns, key)] = value

    def append_event(self, ns, key, entry):
        self.events.setdefault((ns, key), []).append(entry)

    def read_events(self, ns, key):
        return list(self.events.get((ns, key), []))


_PATCHED_MODULES = (memory, task_tracker, persona, heartbeat, followups)


class _ProactivityBase(unittest.TestCase):
    def setUp(self):
        self.store = _FakeStore()
        self._orig = {m: m.state_store for m in _PATCHED_MODULES}
        for m in _PATCHED_MODULES:
            m.state_store = self.store  # type: ignore[assignment]

    def tearDown(self):
        for m, orig in self._orig.items():
            m.state_store = orig


class HeartbeatTest(_ProactivityBase):
    def test_stays_quiet_and_never_calls_llm_when_nothing_due(self):
        calls = {"n": 0}

        def llm(system, user):
            calls["n"] += 1
            return '{"speak": true, "message": "hi"}'

        result = heartbeat.run_heartbeat(llm=llm)
        self.assertFalse(result["spoke"])
        self.assertEqual(calls["n"], 0)  # no LLM spend on a calm, empty day

    def test_disabled_toggle_silences_it(self):
        memory.store_decision("Call mom", scope="today")  # something to check
        heartbeat.set_enabled(False)
        result = heartbeat.run_heartbeat(llm=lambda s, u: '{"speak": true, "message": "x"}')
        self.assertFalse(result["spoke"])
        self.assertEqual(result["reason"], "disabled")

    def test_speaks_when_model_decides_to(self):
        memory.store_decision("Hit the gym", scope="today")

        def llm(system, user):
            # The persona voice is threaded into the system prompt.
            assert "cat" in system.lower()
            assert "Hit the gym" in user
            return '{"speak": true, "message": "I did NOT wake up at 4:30 for you to skip the gym."}'

        result = heartbeat.run_heartbeat(llm=llm)
        self.assertTrue(result["spoke"])
        self.assertIn("gym", result["message"].lower())

    def test_respects_model_choosing_silence(self):
        memory.store_decision("Something minor", scope="this_week")
        result = heartbeat.run_heartbeat(llm=lambda s, u: '{"speak": false, "message": ""}')
        self.assertFalse(result["spoke"])
        self.assertEqual(result["reason"], "stayed quiet")


class FollowupTest(_ProactivityBase):
    def test_sweep_surfaces_only_overdue_open(self):
        past = (user_profile.now() - dt.timedelta(hours=1)).isoformat()
        future = (user_profile.now() + dt.timedelta(hours=1)).isoformat()
        overdue = followups.create("emailed the accountant", "did they reply?", past)
        followups.create("pinged the designer", "any update?", future)

        due = followups.sweep()
        self.assertEqual([f["id"] for f in due], [overdue["id"]])

    def test_resolve_and_resolve_matching_close_the_loop(self):
        past = (user_profile.now() - dt.timedelta(hours=1)).isoformat()
        f = followups.create("sent the invoice", "was it paid?", past)

        self.assertEqual(len(followups.list_open()), 1)
        self.assertEqual(followups.resolve_matching("invoice"), 1)
        self.assertEqual(followups.list_open(), [])
        self.assertFalse(followups.resolve(f["id"]))  # already resolved

    def test_snooze_pushes_due_forward(self):
        past = (user_profile.now() - dt.timedelta(hours=2)).isoformat()
        f = followups.create("booked the call", "confirmed?", past)
        followups.snooze(f["id"], hours=6)
        self.assertEqual(followups.sweep(), [])  # no longer overdue


class TaskRolloverTest(_ProactivityBase):
    def test_priority_tier_and_first_seen_on_add(self):
        t = task_tracker.add_task("Pay rent", priority_tier=0)
        self.assertEqual(t["priority_tier"], 0)
        self.assertEqual(t["rollover_count"], 0)
        self.assertTrue(t["first_seen"])

    def test_unfinished_tasks_roll_over_with_incrementing_age(self):
        today = user_profile.today()
        yesterday = today - dt.timedelta(days=1)
        # Seed yesterday with one done + one undone task.
        self.store.json[(task_tracker.NAMESPACE, yesterday.isoformat())] = [
            {"id": 0, "task": "Done thing", "done": True, "first_seen": yesterday.isoformat()},
            {"id": 1, "task": "Lingering thing", "done": False,
             "first_seen": yesterday.isoformat(), "rollover_count": 0},
        ]
        rolled = task_tracker.initialize_daily_tasks([])
        carried = [t for t in rolled if t["task"] == "Lingering thing"]
        self.assertEqual(len(carried), 1)
        self.assertTrue(carried[0]["rolled_over"])
        self.assertEqual(carried[0]["rollover_count"], 1)
        self.assertNotIn("Done thing", [t["task"] for t in rolled])  # done doesn't roll

    def test_format_shows_rollover_age_and_orders_by_tier(self):
        today = user_profile.today()
        self.store.json[(task_tracker.NAMESPACE, today.isoformat())] = [
            {"id": 0, "task": "low prio", "done": False, "priority_tier": 3,
             "first_seen": today.isoformat(), "rolled_over": False},
            {"id": 1, "task": "urgent old", "done": False, "priority_tier": 0,
             "first_seen": (today - dt.timedelta(days=2)).isoformat(),
             "rolled_over": True, "rollover_count": 2},
        ]
        out = task_tracker.format_tasks()
        # Urgent (tier 0) should be listed before the low-prio one.
        self.assertLess(out.index("urgent old"), out.index("low prio"))
        self.assertIn("day 3", out)  # 2 days old → "day 3"


if __name__ == "__main__":
    unittest.main()
