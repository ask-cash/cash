"""
test_model_catalog.py — LLM provider/model catalog.

Structural invariants for services.providers.catalog: every provider has models +
a valid default, ids are unique per provider, metadata is sane, and the
display-name / platform-auth / default maps cover every provider.

Run:  ./venv/bin/python -m unittest tests.test_model_catalog -v
"""

import unittest

from services.providers import catalog


class CatalogStructureTest(unittest.TestCase):
    def test_every_provider_has_a_default_in_its_model_list(self):
        for provider, models in catalog.MODELS_BY_PROVIDER.items():
            default = catalog.get_default_model_for_provider(provider)
            self.assertIsNotNone(default, f"{provider} has no default")
            if not models:
                # e.g. openai-compatible is intentionally empty with a "" default.
                self.assertEqual(default, "", f"{provider} empty but non-empty default")
                continue
            ids = {m.id for m in models}
            self.assertIn(default, ids, f"{provider} default {default!r} not in its models")

    def test_model_ids_unique_within_provider(self):
        for provider, models in catalog.MODELS_BY_PROVIDER.items():
            ids = [m.id for m in models]
            self.assertEqual(len(ids), len(set(ids)), f"duplicate ids in {provider}")

    def test_maps_cover_every_provider(self):
        provs = set(catalog.MODELS_BY_PROVIDER)
        self.assertEqual(provs, set(catalog.DEFAULT_MODEL_BY_PROVIDER))
        self.assertEqual(provs, set(catalog.PROVIDER_DISPLAY_NAMES))
        self.assertEqual(provs, set(catalog.PROVIDER_SUPPORTS_PLATFORM_AUTH))

    def test_metadata_is_sane(self):
        for provider, models in catalog.MODELS_BY_PROVIDER.items():
            for m in models:
                self.assertGreater(m.context_window_tokens, 0, m.id)
                self.assertGreater(m.max_output_tokens, 0, m.id)
                self.assertLessEqual(
                    m.default_context_window_tokens, m.context_window_tokens, m.id)
                self.assertTrue(m.display_name, m.id)


class LookupTest(unittest.TestCase):
    def test_find_model_by_id(self):
        m = catalog.find_model("claude-opus-4-8")
        self.assertIsNotNone(m)
        self.assertEqual(m.display_name, "Claude Opus 4.8")
        self.assertTrue(m.supports_thinking)

    def test_find_model_scoped_to_provider(self):
        # The same display concept exists under both anthropic and openrouter;
        # scoping resolves the right id namespace.
        self.assertIsNotNone(catalog.find_model("claude-opus-4-8", provider="anthropic"))
        self.assertIsNone(catalog.find_model("claude-opus-4-8", provider="openrouter"))
        self.assertIsNotNone(catalog.find_model("anthropic/claude-opus-4.8", provider="openrouter"))

    def test_unknown_model(self):
        self.assertIsNone(catalog.find_model("gpt-does-not-exist"))
        self.assertFalse(catalog.is_known_model("gpt-does-not-exist"))

    def test_display_name_falls_back_to_id(self):
        self.assertEqual(catalog.provider_display_name("anthropic"), "Anthropic")
        self.assertEqual(catalog.provider_display_name("made-up"), "made-up")

    def test_platform_auth_flags(self):
        self.assertTrue(catalog.provider_supports_platform_auth("anthropic"))
        self.assertFalse(catalog.provider_supports_platform_auth("openrouter"))
        self.assertFalse(catalog.provider_supports_platform_auth("made-up"))

    def test_adaptive_thinking_flag_carried(self):
        self.assertTrue(catalog.find_model("claude-fable-5").adaptive_thinking_only)
        self.assertFalse(catalog.find_model("claude-opus-4-8").adaptive_thinking_only)

    def test_exposed_via_providers_package(self):
        from services import providers
        self.assertIs(providers.find_model, catalog.find_model)
        self.assertIn("anthropic", providers.MODELS_BY_PROVIDER)


if __name__ == "__main__":
    unittest.main()
