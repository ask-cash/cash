"""
test_connections.py — the per-tenant integration connection ledger (real DB).

Exercises services.integrations.connections against a throwaway SQLite DB:
set/get status, the None-when-unrecorded contract, tenant isolation, and that
the ledger overrides credential auto-detection in tokens.is_connected.

Run:  ./venv/bin/python -m unittest tests.test_connections -v
"""

import dataclasses
import os
import tempfile
import unittest

import services.db as db
from services.config import settings as _real_settings
from services.tenancy import tenant_context


class ConnectionsLedgerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        path = os.path.join(self._tmp.name, "conns.db")
        self._orig = db.settings
        db.settings = dataclasses.replace(_real_settings, database_url="", sqlite_path=path)
        db.reset_bootstrap_state_for_tests()
        from services.integrations import connections
        self.conns = connections

    def tearDown(self):
        db.settings = self._orig
        db.reset_bootstrap_state_for_tests()
        self._tmp.cleanup()

    def test_unrecorded_is_none(self):
        with tenant_context("t1"):
            self.assertIsNone(self.conns.get_status("google_calendar"))

    def test_set_and_get(self):
        with tenant_context("t1"):
            self.conns.set_status("google_calendar", True)
            self.assertTrue(self.conns.get_status("google_calendar"))
            self.conns.set_status("google_calendar", False)
            self.assertFalse(self.conns.get_status("google_calendar"))

    def test_status_map(self):
        with tenant_context("t1"):
            self.conns.set_status("google_calendar", True)
            self.conns.set_status("discord", False)
            self.assertEqual(
                self.conns.status_map(), {"google_calendar": True, "discord": False})

    def test_tenant_isolation(self):
        with tenant_context("t1"):
            self.conns.set_status("google_calendar", True)
        with tenant_context("t2"):
            # A different tenant sees no record for the same provider.
            self.assertIsNone(self.conns.get_status("google_calendar"))

    def test_ledger_overrides_credential_detection(self):
        from services.integrations import tokens
        # A stored token would auto-detect as connected...
        vault = type("V", (), {"get_json": lambda self, n, **k: {"t": 1} if n == "google_token" else None,
                               "get_secret": lambda self, n, **k: None})()
        orig_vault = tokens.secret_vault
        tokens.secret_vault = vault
        # ...but an explicit "disconnected" in the ledger wins.
        try:
            with tenant_context("t1"):
                import dataclasses as _dc
                p = tokens.registry._PROVIDERS["google_calendar"]
                tokens.registry._PROVIDERS["google_calendar"] = _dc.replace(p, legacy_token_path=None)
                self.assertTrue(tokens.is_connected("google_calendar"))  # auto-detected
                self.conns.set_status("google_calendar", False)
                self.assertFalse(tokens.is_connected("google_calendar"))  # ledger wins
                tokens.registry._PROVIDERS["google_calendar"] = p
        finally:
            tokens.secret_vault = orig_vault


if __name__ == "__main__":
    unittest.main()
