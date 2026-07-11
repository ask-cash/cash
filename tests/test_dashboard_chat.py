"""
test_dashboard_chat.py — dashboard web-chat service logic.

Covers chat_reply routing a browser turn through the (injected) owner brain,
sharing one memory with the other surfaces (the turn is logged and memory ops
applied), the empty-message guard, and the CSRF token bound to the session.
Framework-free: targets services.dashboard, no fastapi. Stdlib unittest with an
in-memory state_store fake.

Run:  ./venv/bin/python -m unittest tests.test_dashboard_chat -v
"""

import unittest

from services import dashboard as svc
from services import memory


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


class ChatReplyTest(unittest.TestCase):
    def setUp(self):
        self.store = _FakeStore()
        self._orig = memory.state_store
        memory.state_store = self.store

    def tearDown(self):
        memory.state_store = self._orig

    def test_returns_reply_and_shares_memory(self):
        def interpret(message):
            self.assertEqual(message, "hey cash")
            return {
                "action": "chat",
                "reply": "meow, noted 🐾",
                "memory_ops": [{"op": "store_fact", "fact": "likes chai", "category": "preference"}],
            }

        out = svc.chat_reply("pers_1", "default", "hey cash", interpret=interpret)
        self.assertEqual(out["reply"], "meow, noted 🐾")
        self.assertEqual(out["action"], "chat")

        # The turn landed in the same memory Telegram/Discord use.
        facts = memory.get_facts()
        self.assertTrue(any("chai" in f["fact"] for f in facts))
        convos = memory.get_recent_conversations()
        texts = [c["text"] for c in convos]
        self.assertIn("hey cash", texts)          # user turn logged
        self.assertIn("meow, noted 🐾", texts)      # assistant turn logged
        # And it's tagged as coming from the dashboard surface.
        user_turn = next(c for c in convos if c["text"] == "hey cash")
        self.assertEqual(user_turn["metadata"]["surface"], "dashboard")

    def test_empty_message_short_circuits(self):
        called = {"n": 0}

        def interpret(_):
            called["n"] += 1
            return {"reply": "should not run"}

        out = svc.chat_reply("pers_1", "default", "   ", interpret=interpret)
        self.assertEqual(out["reply"], "")
        self.assertEqual(called["n"], 0)


class CsrfTest(unittest.TestCase):
    def test_token_bound_to_session_and_verifies(self):
        t1 = svc.csrf_token("session-abc")
        self.assertEqual(t1, svc.csrf_token("session-abc"))       # stable per session
        self.assertNotEqual(t1, svc.csrf_token("session-xyz"))    # differs per session
        self.assertTrue(svc.verify_csrf("session-abc", t1))
        self.assertFalse(svc.verify_csrf("session-abc", "forged"))
        self.assertFalse(svc.verify_csrf("session-abc", ""))


if __name__ == "__main__":
    unittest.main()
