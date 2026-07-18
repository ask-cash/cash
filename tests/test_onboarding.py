"""
test_onboarding.py — Onboarding flow, signed links, profiles, and routing.

The flow state machine and link signing are pure; profiles/runtime use a
throwaway SQLite DB (same pattern as test_identity_resolution) so nothing
touches real customer data.

Run:  ./venv/bin/python -m unittest tests.test_onboarding -v
"""

import dataclasses
import os
import tempfile
import time
import unittest
from types import SimpleNamespace

import services.db as db
from services.config import settings as _real_settings


# --- pure: links -----------------------------------------------------------

class LinkTokenTest(unittest.TestCase):
    def setUp(self):
        from services.onboarding import links
        self.links = links

    def test_token_round_trips(self):
        tok = self.links.make_token("pers_abc", tenant_id="t1")
        payload = self.links.verify_token(tok)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["pid"], "pers_abc")
        self.assertEqual(payload["tid"], "t1")

    def test_expired_token_rejected(self):
        past = time.time() - 10
        tok = self.links.make_token("pers_abc", ttl_hours=-1, now=time.time())
        self.assertIsNone(self.links.verify_token(tok))
        # Explicit clock: a token minted now is invalid 100h later.
        tok2 = self.links.make_token("pers_abc", ttl_hours=1, now=1000)
        self.assertIsNone(self.links.verify_token(tok2, now=1000 + 3 * 3600))

    def test_tampered_token_rejected(self):
        tok = self.links.make_token("pers_abc")
        body, _, sig = tok.partition(".")
        forged = body[:-2] + "XY" + "." + sig
        self.assertIsNone(self.links.verify_token(forged))
        self.assertIsNone(self.links.verify_token("garbage"))
        self.assertIsNone(self.links.verify_token(""))


# --- pure: flow state machine ---------------------------------------------

class FlowTest(unittest.TestCase):
    def setUp(self):
        from services.onboarding import flow
        from services.onboarding.profiles import CustomerProfile, STATUS_NEW
        self.flow = flow
        self.CustomerProfile = CustomerProfile
        self.profile = CustomerProfile(person_id="pers_1", status=STATUS_NEW)

    def _say(self, text):
        res = self.flow.advance(self.profile, text)
        self.profile = res.profile
        return res

    def test_happy_path_collects_all_fields_then_requests_link(self):
        self._say("hi")                       # greet, ask name
        self.assertEqual(self.profile.step, "name")
        self._say("Aria")
        self.assertEqual(self.profile.name, "Aria")
        self._say("aria@example.com")
        self.assertEqual(self.profile.email, "aria@example.com")
        self._say("Asia/Kolkata")
        self.assertEqual(self.profile.timezone, "Asia/Kolkata")
        res = self._say("scheduling")
        self.assertEqual(self.profile.use_case, "scheduling")
        self.assertTrue(res.link_required)
        self.assertTrue(res.collection_complete)
        self.assertEqual(self.profile.status, "awaiting_setup")

    def test_invalid_email_reasks(self):
        self._say("hi"); self._say("Aria")
        res = self._say("not-an-email")
        self.assertIsNone(self.profile.email)
        self.assertEqual(self.profile.step, "email")
        self.assertIn("email", res.reply.lower())

    def test_invalid_timezone_reasks(self):
        self._say("hi"); self._say("Aria"); self._say("aria@example.com")
        res = self._say("Mars/Olympus")
        self.assertIsNone(self.profile.timezone)
        self.assertEqual(self.profile.step, "timezone")

    def test_awaiting_setup_resends_link(self):
        self.profile.status = "awaiting_setup"
        res = self.flow.advance(self.profile, "you there?")
        self.assertTrue(res.link_required)


# --- DB-backed: profiles + runtime ----------------------------------------

class _TempDBTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        path = os.path.join(self._tmp.name, "t.db")
        self._orig = db.settings
        db.settings = dataclasses.replace(_real_settings, database_url="", sqlite_path=path)
        db.reset_bootstrap_state_for_tests()
        # In local mode, profiles persist to files under ./user_data/tenants/...
        # chdir into the temp dir so tests never touch real user data.
        self._cwd = os.getcwd()
        os.chdir(self._tmp.name)

    def tearDown(self):
        os.chdir(self._cwd)
        db.settings = self._orig
        db.reset_bootstrap_state_for_tests()
        self._tmp.cleanup()


class ProfileLifecycleTest(_TempDBTest):
    def test_create_update_activate(self):
        from services.onboarding import profiles
        self.assertIsNone(profiles.get_profile("pers_x"))
        p = profiles.get_or_create("pers_x")
        self.assertEqual(p.status, profiles.STATUS_NEW)
        self.assertFalse(profiles.is_registered("pers_x"))

        profiles.mark_integration_connected("pers_x", "google_calendar")
        self.assertTrue(profiles.get_profile("pers_x").connected("google_calendar"))

        profiles.mark_active("pers_x")
        self.assertTrue(profiles.is_registered("pers_x"))


class RuntimeRoutingTest(_TempDBTest):
    def _ev(self, text="", is_owner=False, is_direct=True):
        return SimpleNamespace(text=text, is_owner=is_owner, is_direct=is_direct)

    def test_owner_passes_through(self):
        from services.onboarding import runtime
        self.assertFalse(runtime.route(self._ev("hi", is_owner=True), "pers_owner").handled)

    def test_public_channel_passes_through(self):
        from services.onboarding import runtime
        self.assertFalse(runtime.route(self._ev("hi", is_direct=False), "pers_a").handled)

    def test_new_user_is_onboarded_and_link_issued(self):
        from services import tenant_registry
        from services.config import settings
        from services.onboarding import runtime, profiles
        # Walk the new user through onboarding.
        for msg in ["hi", "Bob", "bob@example.com", "America/New_York", "reminders"]:
            res = runtime.route(self._ev(msg), "pers_b")
            self.assertTrue(res.handled)
        last = res.reply
        self.assertIn("/onboard/", last)  # link appended
        self.assertEqual(profiles.get_profile("pers_b").status, profiles.STATUS_AWAITING_SETUP)
        self.assertEqual(
            tenant_registry.get_tenant(settings.default_tenant_id).timezone,
            "America/New_York",
        )

    def test_active_customer_passes_to_assistant(self):
        from services.onboarding import runtime, profiles
        profiles.get_or_create("pers_c")
        profiles.mark_active("pers_c")
        self.assertFalse(runtime.route(self._ev("hello"), "pers_c").handled)

    def test_onboarding_disabled_passes_through(self):
        from services.onboarding import runtime
        orig = runtime.settings
        runtime.settings = dataclasses.replace(orig, onboarding_enabled=False)
        try:
            self.assertFalse(runtime.route(self._ev("hi"), "pers_d").handled)
        finally:
            runtime.settings = orig


if __name__ == "__main__":
    unittest.main()
