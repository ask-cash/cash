"""
test_memory_v2.py — Structured Memory v2 (Feature 2).

Covers: content-hash dedup + kinds on facts/decisions, the bounded brief
compiler, the gated archive recall, the idempotent backfill, and the injectable
reducer. Uses stdlib unittest with an in-memory state_store fake (no DB, no
network), matching the project's test conventions.

Run:  ./venv/bin/python -m unittest tests.test_memory_v2 -v
"""

import unittest

from services import memory, memory_brief, memory_recall, memory_reducer


class _FakeStore:
    """Minimal in-memory stand-in for services.state_store."""

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


class _MemoryTestBase(unittest.TestCase):
    def setUp(self):
        self.store = _FakeStore()
        # Every module reads state_store through its own import; patch each.
        self._patched = [memory.state_store, memory_reducer.state_store]
        for mod in (memory, memory_reducer):
            mod.state_store = self.store  # type: ignore[assignment]

    def tearDown(self):
        memory.state_store, memory_reducer.state_store = self._patched


class DedupAndKindsTest(_MemoryTestBase):
    def test_facts_dedup_by_fingerprint_and_carry_kind(self):
        memory.store_fact("Prefers morning workouts", category="preference", source_message="m1")
        # Same content, different spacing/case → deduped, not a second row.
        memory.store_fact("prefers   MORNING workouts", category="preference", source_message="m2")
        facts = memory.get_facts()
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["kind"], "semantic")
        self.assertIn("m1", facts[0]["sources"])
        self.assertIn("m2", facts[0]["sources"])  # new source attributed on dedup

    def test_rule_category_maps_to_procedural(self):
        rec = memory.store_fact("Never risk more than 2% per trade", category="rule")
        self.assertEqual(rec["kind"], "procedural")

    def test_active_decision_dedups_but_new_after_fulfill(self):
        memory.store_decision("Eat clean this week", scope="this_week")
        memory.store_decision("eat clean this week", scope="this_week")
        self.assertEqual(len(memory.get_active_decisions()), 1)

        memory.fulfill_decision("Eat clean this week")
        # Restating after fulfilling is a genuinely new intention.
        memory.store_decision("Eat clean this week", scope="this_week")
        active = [d for d in memory.get_active_decisions() if not d.get("fulfilled")]
        self.assertEqual(len(active), 1)


class BackfillTest(_MemoryTestBase):
    def test_backfill_is_idempotent(self):
        # Seed legacy records with no kind/fingerprint.
        self.store.json[(memory.NAMESPACE, "facts")] = [
            {"fact": "Lives in Bangalore", "category": "general", "learned_on": "2026-01-01"}
        ]
        self.store.json[(memory.NAMESPACE, "decisions")] = [
            {"decision": "Ship v2", "scope": "this_week", "expires": "9999-12-31", "fulfilled": False}
        ]
        first = memory.backfill_kinds()
        self.assertEqual(first["facts_updated"], 1)
        self.assertEqual(first["decisions_updated"], 1)
        self.assertEqual(memory.get_facts()[0]["kind"], "semantic")

        second = memory.backfill_kinds()  # nothing left to do
        self.assertEqual(second["facts_updated"], 0)
        self.assertEqual(second["decisions_updated"], 0)


class BriefTest(_MemoryTestBase):
    def test_brief_shows_open_loops_and_facts_but_is_bounded(self):
        memory.store_decision("Call mom tonight", scope="today")
        memory.store_fact("Trades NIFTY options", category="general")
        brief = memory_brief.build_brief()
        self.assertIn("OPEN LOOPS", brief)
        self.assertIn("Call mom tonight", brief)
        self.assertIn("Trades NIFTY options", brief)

    def test_fulfilled_decisions_are_not_open_loops(self):
        memory.store_decision("Meditate", scope="today")
        memory.fulfill_decision("Meditate")
        brief = memory_brief.build_brief()
        self.assertNotIn("OPEN LOOPS", brief)

    def test_empty_brief(self):
        self.assertEqual(memory_brief.build_brief(), "No memory yet — fresh start.")


class RecallGateTest(_MemoryTestBase):
    def test_gate_fires_only_on_past_reference_language(self):
        self.assertTrue(memory_recall.should_recall("did I say I'd call mom?"))
        self.assertTrue(memory_recall.should_recall("you told me to skip sugar"))
        self.assertFalse(memory_recall.should_recall("create a meeting at 3pm"))
        self.assertFalse(memory_recall.should_recall("what's my day look like"))

    def test_recall_returns_source_linked_hits(self):
        memory.log_message("user", "I want to call mom this weekend")
        memory.store_fact("Mom's birthday is in July", category="person")
        block = memory_recall.recall_block("did I say something about mom?")
        self.assertIn("<supporting_recall>", block)
        self.assertIn("mom", block.lower())

    def test_closed_gate_returns_empty(self):
        memory.store_fact("Loves espresso", category="preference")
        self.assertEqual(memory_recall.recall_block("add buy coffee to my list"), "")


class ReducerTest(_MemoryTestBase):
    def test_reducer_applies_ops_from_injected_llm(self):
        memory.log_message("user", "I've decided to wake up at 6am every day")
        memory.log_message("user", "also I really dislike surprise meetings")

        def fake_llm(system, user):
            return (
                '[{"op":"store_decision","decision":"Wake up at 6am daily","scope":"permanent"},'
                '{"op":"store_fact","fact":"Dislikes surprise meetings","category":"preference"}]'
            )

        report = memory_reducer.run_reducer(llm=fake_llm)
        self.assertEqual(report["applied"], 2)
        facts = [f["fact"] for f in memory.get_facts()]
        self.assertIn("Dislikes surprise meetings", facts)

    def test_reducer_cursor_prevents_reprocessing(self):
        memory.log_message("user", "first thing")

        calls = {"n": 0}

        def fake_llm(system, user):
            calls["n"] += 1
            return "[]"

        memory_reducer.run_reducer(llm=fake_llm)
        second = memory_reducer.run_reducer(llm=fake_llm)  # no new turns
        self.assertEqual(second["applied"], 0)
        self.assertEqual(second.get("reason"), "nothing new")
        self.assertEqual(calls["n"], 1)  # llm not called the second time


if __name__ == "__main__":
    unittest.main()
