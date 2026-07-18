"""Existing SQLite installs pick up dashboard chat columns safely."""

from __future__ import annotations

import dataclasses
import os
import sqlite3
import tempfile
import unittest

import services.db as db
from services.config import settings as real_settings


class ChatSchemaMigrationTest(unittest.TestCase):
    def test_postgres_bootstrap_rejects_an_rls_bypass_role(self):
        class Cursor:
            def __init__(self, flags):
                self.flags = flags

            def execute(self, *_args):
                return None

            def fetchone(self):
                return self.flags

        for flags in ((True, False), (False, True)):
            with self.subTest(flags=flags):
                with self.assertRaisesRegex(RuntimeError, "NOSUPERUSER"):
                    db._assert_pg_rls_role(Cursor(flags))

        db._assert_pg_rls_role(Cursor((False, False)))

    def test_pre_chat_schema_is_migrated_before_request_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "old.db")
            conn = sqlite3.connect(path)
            conn.executescript(
                """
                CREATE TABLE accounts (
                    email TEXT PRIMARY KEY, password_hash TEXT, first_name TEXT,
                    last_name TEXT, tenant_id TEXT NOT NULL, person_id TEXT NOT NULL,
                    role TEXT, platforms TEXT, onboarded INTEGER NOT NULL DEFAULT 0,
                    auth_provider TEXT NOT NULL DEFAULT 'password', created_at TEXT NOT NULL
                );
                CREATE TABLE conversations (
                    tenant_id TEXT NOT NULL DEFAULT 'default', id TEXT PRIMARY KEY,
                    title TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE conversation_messages (
                    tenant_id TEXT NOT NULL DEFAULT 'default', id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL, role TEXT NOT NULL,
                    content TEXT NOT NULL, action TEXT, created_at TEXT NOT NULL
                );
                """
            )
            conn.close()

            original = db.settings
            try:
                db.settings = dataclasses.replace(
                    real_settings,
                    database_url="",
                    sqlite_path=path,
                )
                db.reset_bootstrap_state_for_tests()
                db.bootstrap()
                conn = sqlite3.connect(path)
                account_cols = {row[1] for row in conn.execute("PRAGMA table_info(accounts)")}
                conv_cols = {row[1] for row in conn.execute("PRAGMA table_info(conversations)")}
                message_cols = {
                    row[1] for row in conn.execute("PRAGMA table_info(conversation_messages)")
                }
                indexes = {
                    row[1] for row in conn.execute("PRAGMA index_list(conversation_messages)")
                }
                conn.close()
            finally:
                db.settings = original
                db.reset_bootstrap_state_for_tests()

            self.assertIn("plan", account_cols)
            self.assertIn("model_id", conv_cols)
            self.assertIn("request_id", message_cols)
            self.assertIn("input_tokens", message_cols)
            self.assertIn("idx_conv_msg_request", indexes)


if __name__ == "__main__":
    unittest.main()
