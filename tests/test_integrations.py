"""
test_integrations.py — integration registry + TokenManager (Feature 7).

Covers registry provider defs (scopes / unlocks / connect hints), connectivity
resolution over a fake secrets vault, disconnect, credential delegation +
refresh through google_auth, and the Feature 6 link (connecting a provider
unlocks its skill pack). Stdlib unittest with an in-memory vault fake.

Run:  ./venv/bin/python -m unittest tests.test_integrations -v
"""

import dataclasses
import unittest

import services.google_auth as google_auth
from services import integrations
from services.integrations import registry, tokens


class _FakeVault:
    def __init__(self):
        self.json = {}
        self.raw = {}

    def get_json(self, name, *, tenant_id=None):
        return self.json.get(name)

    def get_secret(self, name, *, tenant_id=None):
        return self.raw.get(name)

    def set_secret(self, name, value, *, tenant_id=None):
        self.raw[name] = value

    def delete_secret(self, name, *, tenant_id=None):
        self.json.pop(name, None)
        self.raw.pop(name, None)


class _IntegBase(unittest.TestCase):
    def setUp(self):
        self.vault = _FakeVault()
        self._orig_vault = tokens.secret_vault
        tokens.secret_vault = self.vault

        # Make connectivity purely a function of the fake vault: drop the on-disk
        # legacy-token fallback and the Discord DB probe so a developer's real
        # local token files / dev database can't leak into these assertions.
        self._orig_providers = {}
        for pid in ("google_calendar", "gmail", "outlook"):
            p = registry._PROVIDERS[pid]
            self._orig_providers[pid] = p
            registry._PROVIDERS[pid] = dataclasses.replace(p, legacy_token_path=None)
        self._orig_discord = tokens._discord_connected
        tokens._discord_connected = lambda p: False
        # Neutralise the DB-backed connection ledger so connectivity is a pure
        # function of the fake vault (these tests cover the credential-detection
        # path; the ledger has its own test).
        from services.integrations import connections
        self._connections = connections
        self._orig_get_status = connections.get_status
        self._orig_set_status = connections.set_status
        connections.get_status = lambda pid: None
        connections.set_status = lambda pid, connected: None

    def tearDown(self):
        tokens.secret_vault = self._orig_vault
        for pid, p in self._orig_providers.items():
            registry._PROVIDERS[pid] = p
        tokens._discord_connected = self._orig_discord
        self._connections.get_status = self._orig_get_status
        self._connections.set_status = self._orig_set_status

    def _connect_google(self):
        self.vault.json["google_token"] = {"refresh_token": "r", "token": "t"}


class RegistryTest(_IntegBase):
    def test_builtin_providers_registered(self):
        ids = {p.id for p in registry.all_providers()}
        self.assertLessEqual(
            {"google_calendar", "gmail", "outlook", "discord",
             "slack", "notion", "hubspot", "linear", "twitter"}, ids)

    def test_google_unlocks_calendar_files_and_status(self):
        p = registry.get("google_calendar")
        self.assertEqual(set(p.unlocks), {"calendar", "calendars_status", "files"})
        self.assertIn("https://www.googleapis.com/auth/calendar", p.scopes)
        self.assertEqual(p.secret_name, "google_token")

    def test_planned_providers_not_available(self):
        self.assertFalse(registry.get("notion").available)
        self.assertTrue(registry.get("gmail").available)
        avail = {p.id for p in registry.available_providers()}
        self.assertIn("gmail", avail)
        self.assertNotIn("notion", avail)

    def test_providers_unlocking_pack(self):
        # Calendar pack is unlocked by BOTH google and outlook.
        ids = {p.id for p in registry.providers_unlocking("calendar")}
        self.assertEqual(ids, {"google_calendar", "outlook"})

    def test_connect_url_returns_hint(self):
        self.assertEqual(registry.connect_url("google_calendar"), "/connect_google")
        self.assertIsNone(registry.connect_url("nope"))


class ConnectivityTest(_IntegBase):
    def test_oauth_disconnected_then_connected(self):
        self.assertFalse(tokens.is_connected("google_calendar"))
        self._connect_google()
        self.assertTrue(tokens.is_connected("google_calendar"))

    def test_raw_token_also_counts_as_connected(self):
        self.vault.raw["gmail_token"] = '{"token": "t"}'
        self.assertTrue(tokens.is_connected("gmail"))

    def test_planned_provider_never_connected(self):
        self.assertFalse(tokens.is_connected("notion"))

    def test_connected_providers_lists_only_connected(self):
        self._connect_google()
        self.assertIn("google_calendar", tokens.connected_providers())
        self.assertNotIn("gmail", tokens.connected_providers())

    def test_disconnect_clears_token(self):
        self._connect_google()
        self.assertTrue(tokens.is_connected("google_calendar"))
        self.assertTrue(tokens.disconnect("google_calendar"))
        self.assertFalse(tokens.is_connected("google_calendar"))


class CredentialDelegationTest(_IntegBase):
    def test_credentials_refreshes_via_google_auth(self):
        calls = {}
        sentinel = object()

        def fake_load(secret_name, scopes, legacy_path):
            calls["args"] = (secret_name, tuple(scopes), legacy_path)
            return sentinel  # stands in for a refreshed Credentials object

        orig = google_auth.load_credentials
        google_auth.load_credentials = fake_load
        try:
            result = tokens.credentials("google_calendar")
        finally:
            google_auth.load_credentials = orig

        self.assertIs(result, sentinel)
        self.assertEqual(calls["args"][0], "google_token")
        self.assertIn("https://www.googleapis.com/auth/calendar", calls["args"][1])

    def test_credentials_none_for_non_oauth(self):
        self.assertIsNone(tokens.credentials("outlook"))
        self.assertIsNone(tokens.credentials("discord"))

    def test_store_token_requires_vault_provider(self):
        with self.assertRaises(ValueError):
            tokens.store_token("discord", "{}")

    def test_store_token_delegates_to_google_auth(self):
        saved = {}

        def fake_save(secret_name, creds_json, legacy_path):
            saved["name"] = secret_name
            saved["json"] = creds_json

        orig = google_auth.save_token_json
        google_auth.save_token_json = fake_save
        try:
            tokens.store_token("gmail", '{"token": "t"}')
        finally:
            google_auth.save_token_json = orig
        self.assertEqual(saved["name"], "gmail_token")


class PackUnlockTest(_IntegBase):
    def test_pack_with_no_provider_is_always_unlocked(self):
        self.assertTrue(integrations.is_pack_unlocked("tasks"))
        self.assertTrue(integrations.is_pack_unlocked("core"))

    def test_connecting_provider_unlocks_pack(self):
        self.assertFalse(integrations.is_pack_unlocked("calendar"))
        self.assertFalse(integrations.is_pack_unlocked("files"))
        self._connect_google()
        self.assertTrue(integrations.is_pack_unlocked("calendar"))
        self.assertTrue(integrations.is_pack_unlocked("files"))

    def test_unlocked_pack_ids_excludes_locked(self):
        ids = integrations.unlocked_pack_ids()
        self.assertIn("tasks", ids)
        self.assertNotIn("calendar", ids)  # no integration yet
        self._connect_google()
        self.assertIn("calendar", integrations.unlocked_pack_ids())

    def test_pack_status_shape(self):
        self._connect_google()
        status = integrations.pack_status()
        self.assertTrue(status["calendar"]["unlocked"])
        self.assertIn("google_calendar", status["calendar"]["providers"])
        self.assertIn("google_calendar", status["calendar"]["connected"])
        self.assertTrue(status["tasks"]["unlocked"])
        self.assertEqual(status["tasks"]["providers"], [])


if __name__ == "__main__":
    unittest.main()
