"""
test_identity_resolution.py — Identity resolve() against a throwaway SQLite DB.

Covers the rule from the design doc (§2.1) that's easy to regress: Discord and
Telegram user ids are GLOBAL (same human across servers -> one person), while
Slack/Teams ids are WORKSPACE-SCOPED (same id in two workspaces -> two people).

The test points the data layer at a temp SQLite file so it never touches real
user data. Run:

    ./venv/bin/python -m unittest tests.test_identity_resolution -v
"""

import dataclasses
import os
import tempfile
import unittest

import services.db as db
from services.config import settings as _real_settings


class IdentityResolveTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        path = os.path.join(self._tmp.name, "test_cash.db")
        # Repoint the data layer at a throwaway SQLite file.
        self._orig_settings = db.settings
        db.settings = dataclasses.replace(_real_settings, database_url="", sqlite_path=path)
        db.reset_bootstrap_state_for_tests()
        # people.py imports connect from identity.store, which re-exports db.connect,
        # so patching db.settings is sufficient.
        from services.identity import people as people_mod
        self.people = people_mod

    def tearDown(self):
        db.settings = self._orig_settings
        db.reset_bootstrap_state_for_tests()
        self._tmp.cleanup()

    def test_discord_same_user_two_guilds_is_one_person(self):
        p1 = self.people.resolve(platform="discord", platform_user_id="123",
                                 workspace_id="guildA", display_name="Alice")
        p2 = self.people.resolve(platform="discord", platform_user_id="123",
                                 workspace_id="guildB", display_name="Alice")
        self.assertEqual(p1, p2)

    def test_slack_same_id_two_workspaces_is_two_people(self):
        p1 = self.people.resolve(platform="slack", platform_user_id="U1",
                                 workspace_id="teamA", display_name="Bob")
        p2 = self.people.resolve(platform="slack", platform_user_id="U1",
                                 workspace_id="teamB", display_name="Bob")
        self.assertNotEqual(p1, p2)

    def test_resolve_is_idempotent(self):
        p1 = self.people.resolve(platform="telegram", platform_user_id="555",
                                 display_name="Carol", handle="carol")
        p2 = self.people.resolve(platform="telegram", platform_user_id="555")
        self.assertEqual(p1, p2)

    def test_find_by_hint_is_exact_not_substring(self):
        self.people.resolve(platform="discord", platform_user_id="999",
                            display_name="Priya Sharma", handle="priya")
        # Exact display name / handle match.
        self.assertTrue(self.people.find_by_hint("priya"))
        self.assertTrue(self.people.find_by_hint("Priya Sharma"))
        # Substring must NOT match (the pre-Step-3 collision bug).
        self.assertFalse(self.people.find_by_hint("pri"))


if __name__ == "__main__":
    unittest.main()
