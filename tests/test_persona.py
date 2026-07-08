"""
test_persona.py — Cash's voice is one source of truth and reads as the cat.

Covers Feature 1 (Cash Persona Core): the canonical voice is present in every
mode, the owner-mode system prompt still carries the action contract, proxy mode
stays guarded, and the SOUL/NOW overlays round-trip.

Uses stdlib unittest (no pytest). state_store is swapped for an in-memory fake in
setUp and restored in tearDown, so nothing touches real tenant data.

Run:  ./venv/bin/python -m unittest tests.test_persona -v
"""

import unittest

from services import persona


class VoiceTest(unittest.TestCase):
    """Pure voice checks — no I/O, no store."""

    def test_canonical_voice_is_the_cat_in_every_mode(self):
        for mode in ("owner", "proxy", "customer"):
            voice = persona.persona_voice(mode)
            self.assertIn("cat", voice.lower())
            self.assertIn("4:30", voice)  # her origin story

    def test_mode_frames_differ_appropriately(self):
        owner = persona.persona_voice("owner").lower()
        proxy = persona.persona_voice("proxy").lower()
        customer = persona.persona_voice("customer").lower()

        self.assertIn("guardian", owner)
        self.assertIn("on their behalf", proxy)
        self.assertTrue("guarded" in proxy or "private" in proxy)
        self.assertTrue("never reference" in customer or "their world only" in customer)

    def test_no_professional_chief_of_staff_voice_leaks(self):
        for mode in ("owner", "proxy", "customer"):
            v = persona.persona_voice(mode).lower()
            self.assertNotIn("no slang", v)
            self.assertNotIn("no gimmicks", v)
            self.assertNotIn("chief of staff", v)

    def test_owner_system_prompt_keeps_action_contract(self):
        from services import ai_brain

        prompt = ai_brain._build_system_prompt()
        self.assertIn("cat", prompt.lower())      # voice present
        self.assertIn('"action"', prompt)         # action/JSON contract preserved
        self.assertIn("memory_ops", prompt)       # memory contract preserved
        self.assertNotIn("no slang", prompt.lower())


class _FakeStoreTest(unittest.TestCase):
    """Swap state_store for an in-memory dict so overlays can be exercised."""

    def setUp(self):
        self._store = {}
        self._orig_read = persona.state_store.read_json
        self._orig_write = persona.state_store.write_json
        persona.state_store.read_json = (
            lambda ns, key, default=None: self._store.get((ns, key), default)
        )
        persona.state_store.write_json = (
            lambda ns, key, value: self._store.__setitem__((ns, key), value)
        )

    def tearDown(self):
        persona.state_store.read_json = self._orig_read
        persona.state_store.write_json = self._orig_write


class OverlayTest(_FakeStoreTest):
    def test_soul_seeds_then_round_trips(self):
        self.assertEqual(persona.soul_text().strip(), persona.CANONICAL_SOUL.strip())
        self.assertIn((persona.NAMESPACE, "soul"), self._store)  # seeded + persisted

        persona.update_soul("# SOUL\nI have grown fond of naps at 3pm.")
        self.assertIn("naps at 3pm", persona.soul_text())

    def test_now_defaults_empty_then_persists(self):
        self.assertEqual(persona.now_text(), "")
        persona.update_now("Watching the NIFTY close.")
        self.assertIn("NIFTY", persona.now_text())

    def test_system_block_uses_evolved_soul(self):
        self._store[(persona.NAMESPACE, "soul")] = {"body": "# SOUL\nI now judge tardiness harshly."}
        block = persona.persona_system_block("owner", runtime=True)
        self.assertIn("judge tardiness harshly", block)


class DegradeTest(unittest.TestCase):
    def test_system_block_degrades_without_store(self):
        orig = persona.state_store.read_json

        def boom(*a, **k):
            raise RuntimeError("no tenant context")

        persona.state_store.read_json = boom
        try:
            block = persona.persona_system_block("owner", runtime=True)
            self.assertIn("cat", block.lower())  # falls back to canonical voice
        finally:
            persona.state_store.read_json = orig


if __name__ == "__main__":
    unittest.main()
