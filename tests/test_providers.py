"""
test_providers.py — multi-provider LLM abstraction.

Covers the layered config resolver (defaults → profile → per-call override),
call-site dispatch, the pluggable-backend seam, system-block normalisation
(plain vs cache-controlled vs pre-structured), and the unknown-provider error.
Stdlib unittest with a fake backend + a stubbed profile — no network, no SDK.

Run:  ./venv/bin/python -m unittest tests.test_providers -v
"""

import unittest

from services import providers
from services.providers import backends


class _ResolverBase(unittest.TestCase):
    def setUp(self):
        # Isolate from any real tenant profile.
        self._orig_profile = providers._profile_llm
        providers._profile_llm = lambda: {}

    def tearDown(self):
        providers._profile_llm = self._orig_profile


class ResolverTest(_ResolverBase):
    def test_call_site_defaults(self):
        cfg = providers.resolve_config("owner_brain")
        self.assertEqual(cfg["model"], "claude-sonnet-4-6")
        self.assertEqual(cfg["max_tokens"], 1000)
        self.assertEqual(cfg["provider"], "anthropic")

    def test_unknown_call_site_uses_fallback(self):
        cfg = providers.resolve_config("does_not_exist")
        self.assertEqual(cfg["model"], "claude-sonnet-4-6")
        self.assertEqual(cfg["max_tokens"], 1000)

    def test_per_call_override_wins(self):
        cfg = providers.resolve_config("discord_proxy", model="my-model", max_tokens=42)
        self.assertEqual(cfg["model"], "my-model")
        self.assertEqual(cfg["max_tokens"], 42)

    def test_none_overrides_are_ignored(self):
        cfg = providers.resolve_config("owner_brain", model=None, max_tokens=None)
        self.assertEqual(cfg["model"], "claude-sonnet-4-6")

    def test_profile_layer_between_default_and_override(self):
        providers._profile_llm = lambda: {
            "provider": "openai",
            "model": "profile-model",
            "call_sites": {"heartbeat": {"max_tokens": 111}},
        }
        # Global profile model applies...
        cfg = providers.resolve_config("owner_brain")
        self.assertEqual(cfg["provider"], "openai")
        self.assertEqual(cfg["model"], "profile-model")
        # ...per-call-site profile settings apply...
        cfg2 = providers.resolve_config("heartbeat")
        self.assertEqual(cfg2["max_tokens"], 111)
        # ...and a per-call override still beats the profile.
        cfg3 = providers.resolve_config("owner_brain", model="call-model")
        self.assertEqual(cfg3["model"], "call-model")


class DispatchTest(_ResolverBase):
    def setUp(self):
        super().setUp()
        self.calls = []

        def fake(cfg, system, messages, cache_system):
            self.calls.append((cfg, system, messages, cache_system))
            return "FAKE REPLY"

        providers.register_backend("fake", fake)
        self._profile = {"provider": "fake"}
        providers._profile_llm = lambda: self._profile

    def tearDown(self):
        providers._BACKENDS.pop("fake", None)
        super().tearDown()

    def test_send_message_routes_to_selected_backend(self):
        out = providers.send_message("owner_brain", system="S", user="hello")
        self.assertEqual(out, "FAKE REPLY")
        cfg, system, messages, cache_system = self.calls[0]
        self.assertEqual(system, "S")
        self.assertEqual(messages, [{"role": "user", "content": "hello"}])
        self.assertFalse(cache_system)

    def test_messages_passthrough_for_content_blocks(self):
        blocks = [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]
        providers.send_message("file_answer", messages=blocks)
        _, _, messages, _ = self.calls[0]
        self.assertEqual(messages, blocks)

    def test_unknown_provider_raises(self):
        self._profile = {"provider": "nope"}
        with self.assertRaises(ValueError):
            providers.send_message("owner_brain", user="hi")


class SystemNormalisationTest(unittest.TestCase):
    def test_plain_string_passes_through(self):
        self.assertEqual(backends._system_value("hello", False), "hello")

    def test_cache_wraps_string(self):
        val = backends._system_value("hello", True)
        self.assertEqual(val, [{"type": "text", "text": "hello",
                                "cache_control": {"type": "ephemeral"}}])

    def test_prestructured_list_untouched(self):
        block = [{"type": "text", "text": "x", "cache_control": {"type": "ephemeral"}}]
        self.assertIs(backends._system_value(block, True), block)

    def test_none_omitted(self):
        self.assertIsNone(backends._system_value(None, True))

    def test_flatten_content(self):
        self.assertEqual(backends._flatten_content("plain"), "plain")
        self.assertEqual(
            backends._flatten_content([{"type": "text", "text": "a"},
                                       {"type": "image", "source": {}},
                                       {"type": "text", "text": "b"}]),
            "a\nb")


class RegistryTest(unittest.TestCase):
    def test_builtin_backends_registered(self):
        self.assertIn("anthropic", providers.available_backends())
        self.assertIn("openai", providers.available_backends())


if __name__ == "__main__":
    unittest.main()
