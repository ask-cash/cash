"""
test_adapters.py — Adapter normalization + composer rendering (pure paths).

These cover the platform-specific quirks that are easy to get wrong (mention
stripping, bot-message filtering, workspace-id sourcing, threading payloads)
without needing a live platform connection.

Run:  ./venv/bin/python -m unittest tests.test_adapters -v
"""

import unittest

from services.composer.base import PersonContext, render_context_block
from services.platforms.base import OutgoingMessage
from services.platforms.slack_adapter import SlackAdapter
from services.platforms.teams_adapter import TeamsAdapter


class TestSlackAdapter(unittest.TestCase):
    def setUp(self):
        self.a = SlackAdapter(cash_bot_user_id="UCASH", owner_user_id="UBOSS")

    def test_app_mention_normalizes_and_strips_mention(self):
        ev = self.a.normalize({
            "team_id": "T1",
            "event": {
                "type": "app_mention", "user": "U99", "text": "<@UCASH> hey cash",
                "channel": "C1", "ts": "1.2", "channel_type": "channel",
            },
        })
        self.assertIsNotNone(ev)
        self.assertEqual(ev.platform, "slack")
        self.assertEqual(ev.platform_user_id, "U99")
        self.assertEqual(ev.text, "hey cash")
        self.assertTrue(ev.mentions_cash)
        self.assertEqual(ev.workspace_id, "T1")  # workspace-scoped, preserved

    def test_owner_is_flagged(self):
        ev = self.a.normalize({"event": {
            "type": "message", "user": "UBOSS", "text": "hi", "channel": "C1", "ts": "1",
        }})
        self.assertTrue(ev.is_owner)

    def test_bot_and_subtype_messages_are_skipped(self):
        self.assertIsNone(self.a.normalize({"event": {
            "type": "message", "bot_id": "B1", "text": "x", "channel": "C1",
        }}))
        self.assertIsNone(self.a.normalize({"event": {
            "type": "message", "subtype": "message_changed", "user": "U1", "text": "x",
        }}))
        self.assertIsNone(self.a.normalize({"event": {"type": "reaction_added", "user": "U1"}}))

    def test_send_payload_threads_under_source(self):
        ev = self.a.normalize({"event": {
            "type": "message", "user": "U99", "text": "hi", "channel": "C1", "ts": "100.5",
        }})
        payload = self.a.build_send_payload(ev, OutgoingMessage(text="hello"))
        self.assertEqual(payload["channel"], "C1")
        self.assertEqual(payload["thread_ts"], "100.5")

    def test_send_without_fn_raises(self):
        ev = self.a.normalize({"event": {
            "type": "message", "user": "U99", "text": "hi", "channel": "C1", "ts": "1",
        }})
        import asyncio
        with self.assertRaises(RuntimeError):
            asyncio.get_event_loop().run_until_complete(
                self.a.send(ev, OutgoingMessage(text="x"))
            )

    def test_workspace_is_not_global(self):
        self.assertFalse(self.a.workspace_is_global)


class TestTeamsAdapter(unittest.TestCase):
    def setUp(self):
        self.a = TeamsAdapter(cash_bot_id="28:cash", owner_aad_id="aad-boss")

    def test_message_normalizes_and_strips_at_tags(self):
        ev = self.a.normalize({
            "type": "message", "id": "a1", "text": "<at>Cash</at> hello there",
            "from": {"id": "29:u", "aadObjectId": "aad-u", "name": "Bob"},
            "conversation": {"id": "conv1", "conversationType": "channel"},
            "channelData": {"tenant": {"id": "tenant-9"}},
            "entities": [{"type": "mention", "mentioned": {"id": "28:cash"}}],
            "serviceUrl": "https://smba",
        })
        self.assertEqual(ev.platform_user_id, "aad-u")  # AAD oid preferred
        self.assertEqual(ev.text, "hello there")
        self.assertTrue(ev.mentions_cash)
        self.assertEqual(ev.workspace_id, "tenant-9")

    def test_owner_flagged_by_aad_id(self):
        ev = self.a.normalize({
            "type": "message", "id": "a1", "text": "hi",
            "from": {"id": "29:u", "aadObjectId": "aad-boss"},
            "conversation": {"id": "c", "conversationType": "personal"},
        })
        self.assertTrue(ev.is_owner)
        self.assertTrue(ev.is_direct)

    def test_non_message_activity_skipped(self):
        self.assertIsNone(self.a.normalize({"type": "typing"}))
        self.assertIsNone(self.a.normalize({"type": "conversationUpdate"}))

    def test_reply_activity_targets_source_conversation(self):
        ev = self.a.normalize({
            "type": "message", "id": "a1", "text": "hi",
            "from": {"id": "29:u", "aadObjectId": "aad-u"},
            "conversation": {"id": "conv1"},
            "serviceUrl": "https://smba",
        })
        activity = self.a.build_reply_activity(ev, OutgoingMessage(text="pong"))
        self.assertEqual(activity["type"], "message")
        self.assertEqual(activity["text"], "pong")
        self.assertEqual(activity["conversation"], {"id": "conv1"})
        self.assertEqual(activity["replyToId"], "a1")


class TestComposerRendering(unittest.TestCase):
    def test_empty_context_renders_empty(self):
        self.assertEqual(render_context_block(PersonContext(person_id=None)), "")

    def test_summary_preferred_over_recent_lines(self):
        ctx = PersonContext(
            person_id="p", canonical_name="Priya",
            summary_md="- terse\n- hinglish", recent_lines="[d] user: yo",
        )
        block = render_context_block(ctx)
        self.assertIn("WHAT YOU REMEMBER", block)
        self.assertIn("terse", block)
        self.assertNotIn("RECENT MESSAGES", block)  # summary wins

    def test_recent_lines_used_when_no_summary(self):
        ctx = PersonContext(person_id="p", recent_lines="[d] user: yo")
        block = render_context_block(ctx)
        self.assertIn("RECENT MESSAGES", block)

    def test_soft_hints_rendered(self):
        ctx = PersonContext(person_id="p", soft_hints=["high priority"])
        self.assertIn("high priority", render_context_block(ctx))


if __name__ == "__main__":
    unittest.main()
