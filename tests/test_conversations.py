"""
test_conversations.py — persistent chat threads (real DB, SQLite).

Covers create/list/get, message append + ordering, titling from the first
message, tenant isolation, delete cascade, and the send() flow (brain injected).

Run:  ./venv/bin/python -m unittest tests.test_conversations -v
"""

import dataclasses
import os
import tempfile
import unittest

import services.db as db
from services.config import settings as _real_settings
from services.tenancy import tenant_context


class ConversationsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        path = os.path.join(self._tmp.name, "conv.db")
        self._orig = db.settings
        db.settings = dataclasses.replace(_real_settings, database_url="", sqlite_path=path)
        db.reset_bootstrap_state_for_tests()
        from services import conversations
        self.c = conversations

    def tearDown(self):
        db.settings = self._orig
        db.reset_bootstrap_state_for_tests()
        self._tmp.cleanup()

    def test_create_list_and_get(self):
        with tenant_context("t1"):
            conv = self.c.create_conversation()
            self.assertTrue(conv["id"].startswith("conv_"))
            self.assertEqual(conv["title"], "New chat")
            got = self.c.get_conversation(conv["id"])
            self.assertEqual(got["id"], conv["id"])
            self.assertEqual(len(self.c.list_conversations()), 1)

    def test_messages_append_and_order(self):
        with tenant_context("t1"):
            conv = self.c.create_conversation()
            self.c.add_message(conv["id"], "user", "hi")
            self.c.add_message(conv["id"], "assistant", "meow")
            msgs = self.c.get_messages(conv["id"])
            self.assertEqual([m["role"] for m in msgs], ["user", "assistant"])
            self.assertEqual(msgs[0]["content"], "hi")

    def test_tenant_isolation(self):
        with tenant_context("t1"):
            conv = self.c.create_conversation()
        with tenant_context("t2"):
            self.assertEqual(self.c.list_conversations(), [])
            self.assertIsNone(self.c.get_conversation(conv["id"]))

    def test_delete_removes_messages(self):
        with tenant_context("t1"):
            conv = self.c.create_conversation()
            self.c.add_message(conv["id"], "user", "hi")
            self.assertTrue(self.c.delete_conversation(conv["id"]))
            self.assertIsNone(self.c.get_conversation(conv["id"]))
            self.assertEqual(self.c.get_messages(conv["id"]), [])

    def test_send_persists_turn_and_titles(self):
        from services import memory
        # Point memory at the same throwaway DB path via a fake store isn't needed;
        # chat_reply uses state_store (files) which is tenant-scoped. Inject the brain.
        def interpret(_msg):
            return {"action": "chat", "reply": "meow, noted 🐾", "memory_ops": []}

        with tenant_context("t1"):
            conv = self.c.create_conversation()
            out = self.c.send("pers_1", "t1", conv["id"], "remember I like chai", interpret=interpret)
            self.assertEqual(out["reply"], "meow, noted 🐾")
            msgs = self.c.get_messages(conv["id"])
            self.assertEqual([m["role"] for m in msgs], ["user", "assistant"])
            # Thread titled from the first user message.
            self.assertIn("chai", self.c.get_conversation(conv["id"])["title"])
        _ = memory  # (imported to ensure module wiring is intact)


if __name__ == "__main__":
    unittest.main()
