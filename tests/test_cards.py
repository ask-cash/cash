"""
test_cards.py — platform-agnostic rich message cards.

Covers the callback codec (round-trip, size + format guards), the Telegram and
Discord renderers (text + button payloads), and the ready-made builders
(approval, tasks). Pure unit tests — no telegram/discord client.

Run:  ./venv/bin/python -m unittest tests.test_cards -v
"""

import unittest

from services import cards


class CallbackCodecTest(unittest.TestCase):
    def test_round_trip(self):
        data = cards.encode_callback("approve", "delete_event")
        self.assertEqual(data, "card:approve:delete_event")
        self.assertEqual(cards.decode_callback(data), ("approve", "delete_event"))

    def test_empty_arg_round_trips(self):
        data = cards.encode_callback("refresh")
        self.assertEqual(cards.decode_callback(data), ("refresh", ""))

    def test_decode_rejects_foreign_callback(self):
        self.assertIsNone(cards.decode_callback("email_fb:1:important"))
        self.assertIsNone(cards.decode_callback(""))
        self.assertIsNone(cards.decode_callback("card:onlyone"))

    def test_action_with_colon_rejected(self):
        with self.assertRaises(ValueError):
            cards.encode_callback("a:b", "x")

    def test_overlong_callback_rejected(self):
        with self.assertRaises(ValueError):
            cards.encode_callback("approve", "x" * 100)


class TelegramRenderTest(unittest.TestCase):
    def test_text_and_keyboard(self):
        card = cards.Card(
            title="Hi", emoji="📋", body="line", footer="foot",
            button_rows=[[cards.Button("Yes", "approve", "a"),
                          cards.Button("No", "deny", "a")]],
        )
        out = cards.to_telegram(card)
        self.assertIn("📋 Hi", out["text"])
        self.assertIn("line", out["text"])
        self.assertIn("foot", out["text"])
        self.assertEqual(len(out["keyboard"]), 1)
        row = out["keyboard"][0]
        self.assertEqual(row[0], {"text": "Yes", "callback_data": "card:approve:a"})
        self.assertEqual(row[1]["callback_data"], "card:deny:a")

    def test_no_buttons_gives_none_keyboard(self):
        out = cards.to_telegram(cards.Card(title="Plain", body="x"))
        self.assertIsNone(out["keyboard"])


class DiscordRenderTest(unittest.TestCase):
    def test_embed_and_button_hint(self):
        card = cards.Card(
            title="Hi", emoji="🔐", body="body", footer="ft",
            button_rows=[[cards.Button("Approve", "approve", "a")]],
        )
        out = cards.to_discord(card)
        self.assertEqual(out["embed"]["title"], "🔐 Hi")
        self.assertEqual(out["embed"]["description"], "body")
        self.assertEqual(out["embed"]["footer"], {"text": "ft"})
        self.assertIn("[Approve]", out["content"])

    def test_embed_omits_empty_fields(self):
        out = cards.to_discord(cards.Card(title="T"))
        self.assertNotIn("description", out["embed"])
        self.assertNotIn("footer", out["embed"])


class ApprovalCardTest(unittest.TestCase):
    def test_has_approve_and_deny_carrying_action(self):
        card = cards.approval_card("delete_event", note="nuke the 3pm")
        tg = cards.to_telegram(card)
        datas = [b["callback_data"] for row in tg["keyboard"] for b in row]
        self.assertIn("card:approve:delete_event", datas)
        self.assertIn("card:deny:delete_event", datas)
        self.assertIn("delete_event", tg["text"])
        self.assertIn("nuke the 3pm", tg["text"])


class TasksCardTest(unittest.TestCase):
    def _summary(self, pending, done=()):
        return {
            "pending": list(pending),
            "done": list(done),
            "done_count": len(done),
            "total": len(pending) + len(done),
        }

    def test_pending_get_done_buttons(self):
        summary = self._summary(
            pending=[{"id": 1, "task": "gym"}, {"id": 2, "task": "read"}],
            done=[{"id": 0, "task": "meditate"}],
        )
        card = cards.tasks_card(summary)
        tg = cards.to_telegram(card)
        datas = [b["callback_data"] for row in tg["keyboard"] for b in row]
        self.assertIn("card:task_done:1", datas)
        self.assertIn("card:task_done:2", datas)
        self.assertIn("✅ meditate", tg["text"])
        self.assertIn("1/3 done", tg["text"])

    def test_empty_is_friendly_and_buttonless(self):
        card = cards.tasks_card(self._summary(pending=[]))
        tg = cards.to_telegram(card)
        self.assertIsNone(tg["keyboard"])
        self.assertIn("Nothing on the list", tg["text"])

    def test_button_count_capped(self):
        pending = [{"id": i, "task": f"t{i}"} for i in range(20)]
        card = cards.tasks_card(self._summary(pending=pending))
        self.assertEqual(len(card.button_rows), 8)


if __name__ == "__main__":
    unittest.main()
