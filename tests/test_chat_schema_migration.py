"""Existing SQLite installs pick up dashboard chat columns safely."""

from __future__ import annotations

import dataclasses
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

import services.db as db
from services import dispatch_outbox
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

    def test_available_at_expand_keeps_legacy_outbox_writers_working(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "legacy-outbox.db")
            conn = sqlite3.connect(path)
            conn.executescript(
                """
                CREATE TABLE dispatch_outbox (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    job_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    delivered_at TEXT
                );
                INSERT INTO dispatch_outbox (
                    id, tenant_id, job_type, resource_id, payload_json,
                    status, created_at, delivered_at
                ) VALUES (
                    'before-migration', 'tenant-1', 'chat_message', 'job-1',
                    '{}', 'pending', '2026-07-19T00:00:00+00:00', NULL
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

                # Simulate an old pod writing after the new schema expanded:
                # its INSERT still omits available_at.
                with db.connect() as migrated:
                    migrated.execute(
                        """
                        INSERT INTO dispatch_outbox (
                            id, tenant_id, job_type, resource_id, payload_json,
                            status, created_at, delivered_at
                        ) VALUES (?, ?, ?, ?, ?, 'pending', ?, NULL)
                        """,
                        (
                            "old-writer-after-migration",
                            "tenant-1",
                            "media_transcription",
                            "job-2",
                            "{}",
                            "2026-07-19T00:01:00+00:00",
                        ),
                    )

                conn = sqlite3.connect(path)
                available_col = next(
                    row
                    for row in conn.execute("PRAGMA table_info(dispatch_outbox)")
                    if row[1] == "available_at"
                )
                null_count = conn.execute(
                    "SELECT COUNT(*) FROM dispatch_outbox "
                    "WHERE available_at IS NULL"
                ).fetchone()[0]
                conn.close()

                with mock.patch.object(
                    dispatch_outbox,
                    "_now_iso",
                    return_value="2026-07-19T00:02:00+00:00",
                ):
                    pending = dispatch_outbox.pending()
            finally:
                db.settings = original
                db.reset_bootstrap_state_for_tests()

        self.assertEqual(available_col[3], 0)  # nullable during expand
        self.assertEqual(null_count, 2)  # no blocking historical backfill
        self.assertEqual(
            {item["id"] for item in pending},
            {"before-migration", "old-writer-after-migration"},
        )
        self.assertTrue(all(item["availableAt"] == item["createdAt"] for item in pending))
        self.assertNotIn("ALTER COLUMN available_at SET NOT NULL", db._PG_SCHEMA)
        self.assertIn("ALTER COLUMN available_at DROP NOT NULL", db._PG_SCHEMA)
        self.assertNotIn(
            "UPDATE dispatch_outbox SET available_at = created_at",
            db._PG_SCHEMA,
        )
        self.assertNotIn("idx_dispatch_outbox_available", db._PG_SCHEMA)
        self.assertNotIn("idx_dispatch_outbox_ready", db._PG_SCHEMA)


if __name__ == "__main__":
    unittest.main()
