"""
test_routines.py — bounded parallel fan-out routines.

Covers the map fan-out (every item gets a leaf result), the concurrency cap
(never more than N leaves in flight), the hard agent cap (raises past it),
synthesis over leaf outputs, journaling, and cooperative cancellation. Stdlib
unittest with an in-memory state_store fake and a fake LLM — no network.

Run:  ./venv/bin/python -m unittest tests.test_routines -v
"""

import asyncio
import threading
import time
import unittest

from services import routines


class _FakeStore:
    def __init__(self):
        self.json = {}

    def read_json(self, ns, key, default=None):
        return self.json.get((ns, key), default)

    def write_json(self, ns, key, value):
        self.json[(ns, key)] = value


class _Base(unittest.TestCase):
    def setUp(self):
        self.store = _FakeStore()
        self._orig = routines.state_store
        routines.state_store = self.store

    def tearDown(self):
        routines.state_store = self._orig

    def _run(self, coro):
        return asyncio.run(coro)


class MapTest(_Base):
    def test_every_item_gets_a_leaf_result(self):
        def llm(system, user, call_site):
            return f"scored:{user}"

        r = routines.Routine(
            name="score", items=["a", "b", "c"],
            leaf_prompt="rate {item}", synthesis_prompt="",
        )
        out = self._run(routines.run_routine(r, llm=llm))
        self.assertEqual(out["status"], routines.STATUS_DONE)
        self.assertEqual(out["results"], ["scored:rate a", "scored:rate b", "scored:rate c"])
        self.assertIsNone(out["synthesis"])

    def test_synthesis_combines_leaf_outputs(self):
        def llm(system, user, call_site):
            if call_site == "routine_synthesis":
                return f"SUMMARY[{user}]"
            return user.upper()

        r = routines.Routine(
            name="s", items=["x", "y"],
            leaf_prompt="{item}", synthesis_prompt="combine: {results}",
        )
        out = self._run(routines.run_routine(r, llm=llm))
        self.assertEqual(out["results"], ["X", "Y"])
        self.assertIn("combine:", out["synthesis"])
        self.assertIn("- X", out["synthesis"])
        self.assertIn("- Y", out["synthesis"])

    def test_agent_cap_exceeded_raises(self):
        r = routines.Routine(
            name="big", items=[str(i) for i in range(5)],
            leaf_prompt="{item}", max_agents=3,
        )
        with self.assertRaises(ValueError):
            self._run(routines.run_routine(r, llm=lambda s, u, c: u))


class ConcurrencyTest(_Base):
    def test_never_exceeds_concurrency_cap(self):
        lock = threading.Lock()
        state = {"cur": 0, "max": 0}

        def llm(system, user, call_site):
            with lock:
                state["cur"] += 1
                state["max"] = max(state["max"], state["cur"])
            time.sleep(0.02)
            with lock:
                state["cur"] -= 1
            return user

        r = routines.Routine(
            name="c", items=[str(i) for i in range(12)],
            leaf_prompt="{item}", concurrency=3, max_agents=20,
        )
        out = self._run(routines.run_routine(r, llm=llm))
        self.assertEqual(len(out["results"]), 12)
        self.assertLessEqual(state["max"], 3)


class JournalTest(_Base):
    def test_journal_tracks_completion(self):
        r = routines.Routine(name="j", items=["a", "b"], leaf_prompt="{item}")
        out = self._run(routines.run_routine(r, llm=lambda s, u, c: u, routine_id="rid1"))
        status = routines.get_status("rid1")
        self.assertEqual(status["status"], routines.STATUS_DONE)
        self.assertEqual(status["done"], 2)
        self.assertEqual(status["total"], 2)
        self.assertEqual(out["id"], "rid1")


class CancellationTest(_Base):
    def test_precancelled_routine_aborts(self):
        routines.request_cancel("rid2")

        calls = {"n": 0}

        def llm(system, user, call_site):
            calls["n"] += 1
            return user

        r = routines.Routine(name="cancel", items=["a", "b", "c"], leaf_prompt="{item}")
        out = self._run(routines.run_routine(r, llm=llm, routine_id="rid2"))
        self.assertEqual(out["status"], routines.STATUS_CANCELLED)
        self.assertEqual(calls["n"], 0)  # no leaf ran
        self.assertEqual(routines.get_status("rid2")["status"], routines.STATUS_CANCELLED)


if __name__ == "__main__":
    unittest.main()
