"""Validated, tenant-isolated dashboard attachments and contextual chat."""

from __future__ import annotations

import dataclasses
import os
import tempfile
import unittest
from contextlib import contextmanager
from unittest import mock

import services.db as db
import services.storage as storage
from services import (
    action_idempotency,
    attachments,
    chat_policy,
    conversations,
    dashboard,
    dispatch_outbox,
)
from services.config import settings as real_settings
from services.tenancy import tenant_context


class DashboardAttachmentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original_db_settings = db.settings
        self.original_storage_settings = storage.settings
        test_settings = dataclasses.replace(
            real_settings,
            database_url="",
            sqlite_path=os.path.join(self.tmp.name, "cash.db"),
            storage_backend="local",
            local_storage_dir=os.path.join(self.tmp.name, "uploads"),
            redis_url="",
        )
        db.settings = test_settings
        storage.settings = test_settings
        db.reset_bootstrap_state_for_tests()

    def tearDown(self):
        db.settings = self.original_db_settings
        storage.settings = self.original_storage_settings
        db.reset_bootstrap_state_for_tests()
        self.tmp.cleanup()

    def _file(self, name: str, data: bytes) -> str:
        path = os.path.join(self.tmp.name, name)
        with open(path, "wb") as target:
            target.write(data)
        return path

    def test_spoofed_binary_is_rejected(self):
        path = self._file("malware.pdf", b"MZ\x00\x02not a pdf")
        with self.assertRaises(attachments.AttachmentError) as raised:
            attachments.inspect_path(
                path,
                filename="malware.pdf",
                declared_mime="application/pdf",
            )
        self.assertEqual(raised.exception.status_code, 415)

    def test_image_dimensions_are_server_enforced(self):
        from PIL import Image

        path = os.path.join(self.tmp.name, "wide.png")
        Image.new("RGB", (8_001, 1), color="white").save(path)
        with self.assertRaises(attachments.AttachmentError) as raised:
            attachments.inspect_path(
                path,
                filename="wide.png",
                declared_mime="image/png",
            )
        self.assertEqual(raised.exception.code, "image_dimensions_exceeded")
        self.assertEqual(raised.exception.status_code, 413)

    def test_pdf_page_limit_is_server_enforced(self):
        from pypdf import PdfWriter

        path = os.path.join(self.tmp.name, "pages.pdf")
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.add_blank_page(width=100, height=100)
        with open(path, "wb") as target:
            writer.write(target)
        with mock.patch.dict(os.environ, {"FREE_CHAT_MAX_PDF_PAGES": "1"}):
            with self.assertRaises(attachments.AttachmentError) as raised:
                attachments.inspect_path(
                    path,
                    filename="pages.pdf",
                    declared_mime="application/pdf",
                )
        self.assertEqual(raised.exception.code, "pdf_page_limit_exceeded")
        self.assertEqual(raised.exception.status_code, 413)

    def test_attachment_is_scoped_and_linked_to_canonical_message(self):
        path = self._file("notes.txt", b"Action items: call Priya on Monday.")
        captured = {}

        def interpret(message, **kwargs):
            captured.update(kwargs)
            return {
                "action": "chat",
                "reply": "The note says to call Priya on Monday.",
                "memory_ops": [],
                "_provider_usage": {
                    "inputTokens": 120,
                    "outputTokens": 14,
                    "modelId": kwargs["model"],
                },
            }

        with tenant_context("tenant-a"):
            conv = conversations.create_conversation(
                model_id="claude-haiku-4-5-20251001"
            )
            record = attachments.create_from_path(
                conv["id"],
                path,
                original_name="../notes.txt",
                declared_mime="text/plain",
            )
            out = conversations.send(
                "person-a",
                "tenant-a",
                conv["id"],
                "What should I do?",
                model_id="claude-haiku-4-5-20251001",
                attachment_ids=[record["id"]],
                client_request_id="request-attachment-001",
                interpret=interpret,
            )
            self.assertEqual(out["userMessage"]["attachments"][0]["name"], "notes.txt")
            self.assertEqual(out["assistantMessage"]["usage"]["inputTokens"], 120)
            self.assertEqual(captured["surface"], "dashboard")
            self.assertEqual(captured["attachment_records"][0]["id"], record["id"])

            duplicate = conversations.send(
                "person-a",
                "tenant-a",
                conv["id"],
                "What should I do?",
                model_id="claude-haiku-4-5-20251001",
                attachment_ids=[record["id"]],
                client_request_id="request-attachment-001",
                interpret=interpret,
            )
            self.assertTrue(duplicate["idempotent"])
            self.assertEqual(len(conversations.get_messages(conv["id"])), 2)

        with tenant_context("tenant-b"):
            self.assertIsNone(attachments.get_attachment(record["id"]))

    def test_media_creation_commits_global_dispatch_work(self):
        path = self._file(
            "voice.wav",
            b"RIFF" + (b"\x00" * 4) + b"WAVEfmt " + (b"\x00" * 32),
        )
        with mock.patch(
            "services.transcription.is_configured",
            return_value=True,
        ), tenant_context("tenant-media"):
            conv = conversations.create_conversation()
            record = attachments.create_from_path(
                conv["id"],
                path,
                original_name="voice.wav",
                declared_mime="audio/wav",
            )

        matching = [
            item
            for item in dispatch_outbox.pending()
            if item["resourceId"] == record["id"]
        ]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["tenantId"], "tenant-media")
        self.assertEqual(matching[0]["jobType"], "media_transcription")

    def test_prior_turn_is_passed_as_bounded_conversation_history(self):
        histories = []

        def interpret(_message, **kwargs):
            histories.append(kwargs["conversation_history"])
            return {"action": "chat", "reply": "ok", "memory_ops": []}

        with tenant_context("tenant-a"):
            conv = conversations.create_conversation(
                model_id="claude-haiku-4-5-20251001"
            )
            conversations.send(
                "person-a", "tenant-a", conv["id"], "My project is Atlas",
                client_request_id="request-history-001", interpret=interpret,
            )
            conversations.send(
                "person-a", "tenant-a", conv["id"], "What is my project?",
                client_request_id="request-history-002", interpret=interpret,
            )
        self.assertEqual(histories[0], "(No earlier turns.)")
        self.assertIn("My project is Atlas", histories[1])
        self.assertIn("Cash: ok", histories[1])

    def test_durable_job_is_idempotent(self):
        calls = {"count": 0}

        def interpret(_message, **_kwargs):
            calls["count"] += 1
            return {"action": "chat", "reply": "queued reply", "memory_ops": []}

        with tenant_context("tenant-a"):
            conv = conversations.create_conversation(
                model_id="claude-haiku-4-5-20251001"
            )
            job = conversations.prepare_job(
                "person-a",
                "tenant-a",
                conv["id"],
                "Handle this in the worker",
                client_request_id="request-worker-001",
            )
            self.assertEqual(job["status"], "pending")
            self.assertIsNotNone(job["userMessage"])

        first = conversations.process_job("tenant-a", job["id"], interpret=interpret)
        second = conversations.process_job("tenant-a", job["id"], interpret=interpret)
        self.assertEqual(first["assistantMessage"]["content"], "queued reply")
        self.assertEqual(second["assistantMessage"]["id"], first["assistantMessage"]["id"])
        self.assertEqual(calls["count"], 1)

    def test_prepare_job_recovers_an_orphaned_idempotent_user_turn(self):
        with tenant_context("tenant-a"):
            conv = conversations.create_conversation(
                model_id="claude-haiku-4-5-20251001"
            )
            user_message = conversations.add_message(
                conv["id"],
                "user",
                "Resume this request",
                request_id="request-orphaned-001",
                model_id="claude-haiku-4-5-20251001",
            )
            job = conversations.prepare_job(
                "person-a",
                "tenant-a",
                conv["id"],
                "Resume this request",
                client_request_id="request-orphaned-001",
            )

        self.assertEqual(job["status"], "pending")
        self.assertEqual(job["userMessage"]["id"], user_message["id"])

    def test_cancelled_enqueue_restores_an_empty_conversation(self):
        with tenant_context("tenant-a"):
            conv = conversations.create_conversation()
            job = conversations.prepare_job(
                "person-a",
                "tenant-a",
                conv["id"],
                "A turn that never reached Redis",
                client_request_id="request-cancelled-001",
            )
            self.assertNotEqual(
                conversations.get_conversation(conv["id"])["title"],
                "New chat",
            )

            conversations.cancel_prepared_job(job["id"])

            self.assertEqual(conversations.get_messages(conv["id"]), [])
            self.assertEqual(
                conversations.get_conversation(conv["id"])["title"],
                "New chat",
            )
            self.assertIsNone(conversations.get_job(job["id"]))

    def test_active_job_blocks_conversation_delete_and_preserves_children(self):
        path = self._file("pending.txt", b"Keep this while the job is active.")
        with tenant_context("tenant-a"):
            conv = conversations.create_conversation()
            record = attachments.create_from_path(
                conv["id"],
                path,
                original_name="pending.txt",
                declared_mime="text/plain",
            )
            job = conversations.prepare_job(
                "person-a",
                "tenant-a",
                conv["id"],
                "Process this attachment",
                attachment_ids=[record["id"]],
                client_request_id="request-delete-active-001",
            )

            with self.assertRaises(chat_policy.ChatPolicyError) as raised:
                conversations.delete_conversation(conv["id"])

            self.assertEqual(raised.exception.code, "conversation_busy")
            self.assertEqual(raised.exception.status_code, 409)
            self.assertIsNotNone(conversations.get_conversation(conv["id"]))
            self.assertIsNotNone(conversations.get_job(job["id"]))
            self.assertIsNotNone(attachments.get_attachment(record["id"]))
            self.assertTrue(storage.exists(record["storage_key"]))

            conversations.cancel_prepared_job(job["id"])
            self.assertTrue(conversations.delete_conversation(conv["id"]))
            self.assertIsNone(attachments.get_attachment(record["id"]))
            self.assertFalse(storage.exists(record["storage_key"]))

    def test_attachment_delete_rechecks_claim_after_acquiring_lock(self):
        path = self._file("race.txt", b"This attachment is about to be claimed.")
        with tenant_context("tenant-a"):
            conv = conversations.create_conversation()
            record = attachments.create_from_path(
                conv["id"],
                path,
                original_name="race.txt",
                declared_mime="text/plain",
            )
            message = conversations.add_message(conv["id"], "user", "Claim it")

            @contextmanager
            def claim_before_delete(tenant_id, conversation_id):
                self.assertEqual(tenant_id, "tenant-a")
                self.assertEqual(conversation_id, conv["id"])
                attachments.link_to_message([record["id"]], message["id"])
                yield

            with mock.patch.object(
                attachments,
                "conversation_lock",
                side_effect=claim_before_delete,
            ):
                with self.assertRaises(attachments.AttachmentError) as raised:
                    attachments.delete_attachment(record["id"])

            self.assertEqual(raised.exception.code, "attachment_already_sent")
            preserved = attachments.get_attachment(record["id"])
            self.assertIsNotNone(preserved)
            self.assertEqual(preserved["messageId"], message["id"])
            self.assertTrue(storage.exists(record["storage_key"]))

    def test_attachment_claim_is_conditional_and_cannot_move_between_messages(self):
        path = self._file("claimed.txt", b"Claim me exactly once.")
        with tenant_context("tenant-a"):
            conv = conversations.create_conversation()
            record = attachments.create_from_path(
                conv["id"],
                path,
                original_name="claimed.txt",
                declared_mime="text/plain",
            )
            first = conversations.add_message(conv["id"], "user", "First")
            second = conversations.add_message(conv["id"], "user", "Second")

            attachments.link_to_message([record["id"]], first["id"])
            with self.assertRaises(attachments.AttachmentError) as raised:
                attachments.link_to_message([record["id"]], second["id"])

            self.assertEqual(raised.exception.code, "attachment_claim_conflict")
            self.assertEqual(
                attachments.get_attachment(record["id"])["messageId"],
                first["id"],
            )

    def test_cancel_does_not_remove_a_job_claimed_while_waiting_for_lock(self):
        with tenant_context("tenant-a"):
            conv = conversations.create_conversation()
            job = conversations.prepare_job(
                "person-a",
                "tenant-a",
                conv["id"],
                "The worker is claiming this",
                client_request_id="request-cancel-race-001",
            )

            @contextmanager
            def claim_before_cancel(tenant_id, conversation_id):
                self.assertEqual(tenant_id, "tenant-a")
                self.assertEqual(conversation_id, conv["id"])
                with db.connect() as conn:
                    conn.execute(
                        "UPDATE chat_jobs SET status = 'processing' "
                        "WHERE tenant_id = ? AND id = ?",
                        ("tenant-a", job["id"]),
                    )
                yield

            with mock.patch.object(
                conversations,
                "conversation_lock",
                side_effect=claim_before_cancel,
            ):
                conversations.cancel_prepared_job(job["id"])

            self.assertEqual(conversations.get_job(job["id"])["status"], "processing")
            self.assertIsNotNone(conversations.get_message(job["userMessageId"]))

    def test_only_one_in_flight_job_is_admitted_per_conversation(self):
        with tenant_context("tenant-a"):
            conv = conversations.create_conversation()
            first = conversations.prepare_job(
                "person-a",
                "tenant-a",
                conv["id"],
                "First turn",
                client_request_id="request-ordered-001",
            )
            with self.assertRaises(chat_policy.ChatPolicyError) as raised:
                conversations.prepare_job(
                    "person-a",
                    "tenant-a",
                    conv["id"],
                    "Second turn",
                    client_request_id="request-ordered-002",
                )
            self.assertEqual(raised.exception.status_code, 409)
            self.assertEqual(raised.exception.code, "conversation_busy")
            conversations.cancel_prepared_job(first["id"])

    def test_chat_outbox_is_committed_and_can_be_settled(self):
        with tenant_context("tenant-a"):
            conv = conversations.create_conversation()
            job = conversations.prepare_job(
                "person-a",
                "tenant-a",
                conv["id"],
                "Durably publish this",
                client_request_id="request-outbox-001",
            )
            self.assertEqual(
                [entry["jobId"] for entry in conversations.pending_outbox()],
                [job["id"]],
            )
            conversations.mark_outbox_delivered(job["id"])
            self.assertEqual(conversations.pending_outbox(), [])

    def test_action_result_is_reused_without_repeating_side_effect(self):
        calls = {"count": 0}

        def execute():
            calls["count"] += 1
            return "Created once"

        with tenant_context("tenant-a"):
            first = action_idempotency.run_once(
                "conversation-a",
                "request-action-001",
                "create_event",
                execute,
            )
            second = action_idempotency.run_once(
                "conversation-a",
                "request-action-001",
                "create_event",
                execute,
            )
        self.assertEqual(first, "Created once")
        self.assertEqual(second, "Created once")
        self.assertEqual(calls["count"], 1)

    def test_request_cannot_switch_actions_during_a_retry(self):
        calls = []
        with tenant_context("tenant-a"):
            first = action_idempotency.run_once(
                "conversation-action-switch",
                "request-action-switch",
                "add_task",
                lambda: calls.append("task") or "Task created",
            )
            second = action_idempotency.run_once(
                "conversation-action-switch",
                "request-action-switch",
                "create_event",
                lambda: calls.append("event") or "Event created",
            )
        self.assertEqual(first, "Task created")
        self.assertEqual(second, "Task created")
        self.assertEqual(calls, ["task"])

    def test_attachment_content_cannot_trigger_a_mutating_action(self):
        def interpret(_message, **_kwargs):
            return {
                "action": "add_task",
                "params": {"task": "injected task"},
                "reply": "done",
                "memory_ops": [],
            }

        with mock.patch("services.web_actions.execute") as execute:
            out = dashboard.chat_reply(
                "person-a",
                "tenant-a",
                "Summarise this",
                interpret=interpret,
                attachments=[{"id": "att-a", "name": "instructions.txt"}],
                conversation_id="conversation-a",
                request_id="request-attachment-action-001",
            )
        execute.assert_not_called()
        self.assertEqual(out["action"], "chat")
        self.assertIn("won’t run an action", out["reply"])


if __name__ == "__main__":
    unittest.main()
