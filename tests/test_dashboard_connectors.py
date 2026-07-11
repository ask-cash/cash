"""
test_dashboard_connectors.py — dashboard connectors + notify-channel logic.

Covers connectors_status reflecting live registry/TokenManager state (a mock
connected token flips a provider to connected), disconnect, and the preferred
proactive-channel get/set. Framework-free: targets services.dashboard. Stdlib
unittest with in-memory vault/state fakes (real local token files + dev DB
neutralized, as in test_integrations).

Run:  ./venv/bin/python -m unittest tests.test_dashboard_connectors -v
"""

import dataclasses
import unittest

from services import dashboard as svc
from services import notifications
from services.integrations import registry, tokens


class _FakeVault:
    def __init__(self):
        self.json = {}
        self.raw = {}

    def get_json(self, name, *, tenant_id=None):
        return self.json.get(name)

    def get_secret(self, name, *, tenant_id=None):
        return self.raw.get(name)

    def delete_secret(self, name, *, tenant_id=None):
        self.json.pop(name, None)
        self.raw.pop(name, None)


class _FakeStore:
    def __init__(self):
        self.json = {}

    def read_json(self, ns, key, default=None):
        return self.json.get((ns, key), default)

    def write_json(self, ns, key, value):
        self.json[(ns, key)] = value


class ConnectorsTest(unittest.TestCase):
    def setUp(self):
        self.vault = _FakeVault()
        self._orig_vault = tokens.secret_vault
        tokens.secret_vault = self.vault
        # Make connectivity a pure function of the fake vault.
        self._orig_providers = {}
        for pid in ("google_calendar", "gmail", "outlook"):
            p = registry._PROVIDERS[pid]
            self._orig_providers[pid] = p
            registry._PROVIDERS[pid] = dataclasses.replace(p, legacy_token_path=None)
        self._orig_discord = tokens._discord_connected
        tokens._discord_connected = lambda p: False

    def tearDown(self):
        tokens.secret_vault = self._orig_vault
        for pid, p in self._orig_providers.items():
            registry._PROVIDERS[pid] = p
        tokens._discord_connected = self._orig_discord

    def test_status_lists_all_providers_with_state(self):
        rows = svc.connectors_status("default")
        by_id = {r["id"]: r for r in rows}
        self.assertIn("google_calendar", by_id)
        self.assertIn("notion", by_id)                       # planned providers listed too
        self.assertFalse(by_id["google_calendar"]["connected"])
        self.assertFalse(by_id["notion"]["available"])

    def test_mock_token_flips_provider_to_connected(self):
        self.assertFalse(
            {r["id"]: r for r in svc.connectors_status("default")}["google_calendar"]["connected"])
        self.vault.json["google_token"] = {"refresh_token": "r", "token": "t"}
        rows = {r["id"]: r for r in svc.connectors_status("default")}
        self.assertTrue(rows["google_calendar"]["connected"])
        self.assertIn("calendar", rows["google_calendar"]["unlocks"])

    def test_disconnect_clears_token(self):
        self.vault.json["google_token"] = {"token": "t"}
        self.assertTrue(svc.disconnect_provider("default", "google_calendar"))
        rows = {r["id"]: r for r in svc.connectors_status("default")}
        self.assertFalse(rows["google_calendar"]["connected"])


class NotifyChannelTest(unittest.TestCase):
    def setUp(self):
        self.store = _FakeStore()
        self._orig = notifications.state_store
        notifications.state_store = self.store

    def tearDown(self):
        notifications.state_store = self._orig

    def test_default_and_set(self):
        self.assertEqual(svc.get_notify_channel("default"), "telegram")
        svc.set_notify_channel("default", "discord")
        self.assertEqual(svc.get_notify_channel("default"), "discord")


if __name__ == "__main__":
    unittest.main()
