"""
test_accounts.py — dashboard account store (real DB, SQLite backend).

Exercises the actual schema + services.accounts against a throwaway SQLite file:
signup creates a user + tenant + person, passwords are hashed (never stored
plaintext) and verified, duplicate emails are rejected, OAuth accounts are
password-less, and profile updates round-trip. Also covers the session lookup
(person_id → account) the API uses.

Run:  ./venv/bin/python -m unittest tests.test_accounts -v
"""

import dataclasses
import os
import tempfile
import unittest

import services.db as db
from services.config import settings as _real_settings
from services.tenancy import tenant_context


class AccountsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        path = os.path.join(self._tmp.name, "accounts.db")
        self._orig = db.settings
        db.settings = dataclasses.replace(_real_settings, database_url="", sqlite_path=path)
        db.reset_bootstrap_state_for_tests()
        from services import accounts
        self.accounts = accounts

    def tearDown(self):
        db.settings = self._orig
        db.reset_bootstrap_state_for_tests()
        self._tmp.cleanup()

    def test_signup_creates_user_tenant_and_person(self):
        a = self.accounts.create_account(
            "Alice@Example.com ",
            "hunter2!",
            "Alice",
            "Kaur",
            timezone="America/New_York",
        )
        self.assertEqual(a["email"], "alice@example.com")   # normalised
        self.assertEqual(a["timezone"], "America/New_York")
        self.assertTrue(a["tenant_id"])
        self.assertTrue(a["person_id"])
        self.assertFalse(a["onboarded"])
        # A distinct account gets a distinct tenant (isolation).
        b = self.accounts.create_account("bob@example.com", "sekret1", "Bob")
        self.assertNotEqual(a["tenant_id"], b["tenant_id"])

    def test_password_is_hashed_not_stored_plaintext(self):
        self.accounts.create_account("c@example.com", "s3cretpw", "C")
        raw = self.accounts._password_hash("c@example.com")
        self.assertTrue(raw.startswith("pbkdf2$"))
        self.assertNotIn("s3cretpw", raw)

    def test_login_verifies_password(self):
        self.accounts.create_account("d@example.com", "correct-horse", "D")
        self.assertIsNone(self.accounts.verify_login("d@example.com", "wrong"))
        ok = self.accounts.verify_login("d@example.com", "correct-horse")
        self.assertIsNotNone(ok)
        self.assertEqual(ok["email"], "d@example.com")

    def test_duplicate_email_rejected(self):
        self.accounts.create_account("e@example.com", "pw123456", "E")
        with self.assertRaises(ValueError):
            self.accounts.create_account("e@example.com", "pw123456", "E")

    def test_oauth_account_is_passwordless(self):
        a = self.accounts.get_or_create_oauth_account("g@example.com", "Grace")
        self.assertEqual(a["auth_provider"], "google")
        self.assertIsNone(self.accounts._password_hash("g@example.com"))
        # Password login can never succeed on a password-less account.
        self.assertIsNone(self.accounts.verify_login("g@example.com", ""))
        # Idempotent.
        again = self.accounts.get_or_create_oauth_account("g@example.com")
        self.assertEqual(a["person_id"], again["person_id"])

    def test_profile_update_roundtrips(self):
        self.accounts.create_account("h@example.com", "pw123456", "H")
        updated = self.accounts.update_profile(
            "h@example.com", role="Founder", platforms=["Slack", "Telegram"], onboarded=True)
        self.assertEqual(updated["role"], "Founder")
        self.assertEqual(updated["platforms"], ["Slack", "Telegram"])
        self.assertTrue(updated["onboarded"])

    def test_timezone_update_is_validated_and_tenant_isolated(self):
        alice = self.accounts.create_account(
            "alice-tz@example.com",
            "pw123456",
            "Alice",
            timezone="UTC",
        )
        bob = self.accounts.create_account(
            "bob-tz@example.com",
            "pw123456",
            "Bob",
            timezone="Europe/London",
        )

        updated = self.accounts.update_profile(
            alice["email"],
            timezone="Asia/Kolkata",
        )
        self.assertEqual(updated["timezone"], "Asia/Kolkata")
        self.assertEqual(
            self.accounts.get_account(bob["email"])["timezone"],
            "Europe/London",
        )

        with self.assertRaisesRegex(ValueError, "valid IANA"):
            self.accounts.update_profile(
                alice["email"],
                timezone="Mars/Olympus_Mons",
            )
        self.assertEqual(
            self.accounts.get_account(alice["email"])["timezone"],
            "Asia/Kolkata",
        )

    def test_signup_rejects_invalid_timezone_before_creating_account(self):
        with self.assertRaisesRegex(ValueError, "valid IANA"):
            self.accounts.create_account(
                "invalid-tz@example.com",
                "pw123456",
                "Invalid",
                timezone="../../etc/passwd",
            )
        self.assertIsNone(self.accounts.get_account("invalid-tz@example.com"))

    def test_tenant_timezone_wins_over_legacy_profile_document(self):
        from services import state_store, tenant_registry, user_profile

        account = self.accounts.create_account(
            "canonical-tz@example.com",
            "pw123456",
            "Canonical",
            timezone="UTC",
        )
        with tenant_context(account["tenant_id"]):
            state_store.write_json(
                "profile",
                "owner",
                {"timezone": "Europe/Paris", "wake_time": "07:00"},
            )
            self.assertEqual(user_profile.load_profile()["timezone"], "UTC")

            updated = user_profile.save_profile(
                {"timezone": "Asia/Tokyo", "sleep_time": "22:00"}
            )
            stored = state_store.read_json("profile", "owner", default={})

        self.assertEqual(updated["timezone"], "Asia/Tokyo")
        self.assertNotIn("timezone", stored)
        self.assertEqual(stored["wake_time"], "07:00")
        self.assertEqual(stored["sleep_time"], "22:00")
        self.assertEqual(
            tenant_registry.get_tenant(account["tenant_id"]).timezone,
            "Asia/Tokyo",
        )

    def test_lookup_by_person_id(self):
        a = self.accounts.create_account("i@example.com", "pw123456", "I")
        found = self.accounts.get_account_by_person(a["person_id"])
        self.assertEqual(found["email"], "i@example.com")
        self.assertIsNone(self.accounts.get_account_by_person("nope"))


if __name__ == "__main__":
    unittest.main()
