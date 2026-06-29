"""
test_outbound.py — Cross-platform outbound send (Phase 1).

Covers the two pure-ish units of the outbound path without a live Redis or a
live Discord socket:
  - queue.enqueue_outbound / dequeue_outbound / claim_idempotency (fake Redis)
  - discord_adapter.deliver (fake client: cache hit, fetch fallback, clamp, empty)

Run:  ./venv/bin/python -m unittest tests.test_outbound -v
"""

import unittest
from types import SimpleNamespace

from services import queue
from services.platforms.discord_adapter import deliver


class FakeRedis:
    """Minimal in-memory stand-in: lpush/brpop FIFO + SET NX EX."""

    def __init__(self):
        self.lists: dict[str, list] = {}
        self.kv: dict[str, str] = {}

    def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, value)

    def brpop(self, key, timeout=5):
        lst = self.lists.get(key) or []
        if not lst:
            return None
        return (key, lst.pop())  # oldest first → FIFO with lpush

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.kv:
            return None
        self.kv[key] = value
        return True


class TestOutboundQueue(unittest.TestCase):
    def setUp(self):
        self._saved = queue._redis
        queue._redis = FakeRedis()

    def tearDown(self):
        queue._redis = self._saved

    def test_enqueue_dequeue_round_trip(self):
        queue.enqueue_outbound("discord", "tnt_1", {"to": "owner", "text": "hi"})
        job = queue.dequeue_outbound("discord", "tnt_1", timeout=1)
        self.assertIsNotNone(job)
        self.assertEqual(job["platform"], "discord")
        self.assertEqual(job["tenant_id"], "tnt_1")
        self.assertEqual(job["payload"]["text"], "hi")
        # drained
        self.assertIsNone(queue.dequeue_outbound("discord", "tnt_1", timeout=1))

    def test_isolated_per_platform_and_tenant(self):
        queue.enqueue_outbound("discord", "tnt_1", {"text": "a"})
        # different tenant / platform must not see it
        self.assertIsNone(queue.dequeue_outbound("discord", "tnt_2", timeout=1))
        self.assertIsNone(queue.dequeue_outbound("slack", "tnt_1", timeout=1))
        self.assertIsNotNone(queue.dequeue_outbound("discord", "tnt_1", timeout=1))

    def test_fifo_order(self):
        queue.enqueue_outbound("discord", "t", {"text": "first"})
        queue.enqueue_outbound("discord", "t", {"text": "second"})
        self.assertEqual(queue.dequeue_outbound("discord", "t", 1)["payload"]["text"], "first")
        self.assertEqual(queue.dequeue_outbound("discord", "t", 1)["payload"]["text"], "second")

    def test_idempotency_claim_once(self):
        self.assertTrue(queue.claim_idempotency("abc"))   # first time
        self.assertFalse(queue.claim_idempotency("abc"))  # duplicate
        self.assertTrue(queue.claim_idempotency("def"))   # different key
        self.assertTrue(queue.claim_idempotency(""))      # empty key always claims


class TestDiscordDeliver(unittest.IsolatedAsyncioTestCase):
    def _user(self):
        sent = []

        async def send(text):
            sent.append(text)
            return SimpleNamespace(id=4242)

        return SimpleNamespace(send=send, sent=sent)

    async def test_uses_cached_user(self):
        user = self._user()
        client = SimpleNamespace(get_user=lambda uid: user,
                                 fetch_user=None)  # must not be called
        mid = await deliver(client, 123, "hello")
        self.assertEqual(mid, "4242")
        self.assertEqual(user.sent, ["hello"])

    async def test_fetches_when_not_cached(self):
        user = self._user()
        fetched = {}

        async def fetch_user(uid):
            fetched["id"] = uid
            return user

        client = SimpleNamespace(get_user=lambda uid: None, fetch_user=fetch_user)
        await deliver(client, 777, "yo")
        self.assertEqual(fetched["id"], 777)
        self.assertEqual(user.sent, ["yo"])

    async def test_clamps_long_text(self):
        user = self._user()
        client = SimpleNamespace(get_user=lambda uid: user, fetch_user=None)
        await deliver(client, 1, "x" * 5000, max_chars=100)
        self.assertEqual(len(user.sent[0]), 100)
        self.assertTrue(user.sent[0].endswith("…"))

    async def test_empty_text_raises(self):
        client = SimpleNamespace(get_user=lambda uid: self._user(), fetch_user=None)
        with self.assertRaises(ValueError):
            await deliver(client, 1, "   ")


if __name__ == "__main__":
    unittest.main()
