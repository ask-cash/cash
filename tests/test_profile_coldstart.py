"""
test_profile_coldstart.py — a fresh tenant has ZERO routine knowledge.

Guards the cold-start behaviour: no baked-in gym/trading/wake defaults, and the
brain context says "NONE ON FILE" so Cash asks instead of inventing one.

Run:  ./venv/bin/python -m unittest tests.test_profile_coldstart -v
"""

import datetime as dt
import os
import unittest
from unittest import mock

from services import user_profile, ai_brain


class TestHasRoutine(unittest.TestCase):
    def test_empty_profile_has_no_routine(self):
        self.assertFalse(user_profile.has_routine({}))

    def test_name_and_tz_alone_are_not_a_routine(self):
        self.assertFalse(user_profile.has_routine({"name": "Asha", "timezone": "UTC"}))

    def test_any_routine_field_flips_it_true(self):
        self.assertTrue(user_profile.has_routine({"wake_time": "07:00"}))
        self.assertTrue(user_profile.has_routine({"gym": {"days": ["Mon"]}}))
        self.assertTrue(user_profile.has_routine({"trading": {"rules": ["no revenge trades"]}}))
        self.assertTrue(user_profile.has_routine({"default_tasks": [{"task": "standup"}]}))


class TestEnvProfileNoDefaults(unittest.TestCase):
    def test_absent_env_yields_empty_routine(self):
        # Clear env so we see the *code* defaults — there must be no Suhail-ish routine.
        with mock.patch.dict(os.environ, {}, clear=True):
            p = user_profile._env_profile()
        self.assertEqual(p["wake_time"], "")
        self.assertEqual(p["sleep_time"], "")
        self.assertEqual(p["gym"]["default_time"], "")
        self.assertEqual(p["gym"]["days"], [])
        self.assertEqual(p["gym"]["duration_minutes"], 0)
        self.assertEqual(p["trading"]["market_open"], "")
        self.assertEqual(p["trading"]["rules"], [])
        self.assertEqual(p["default_tasks"], [])
        self.assertFalse(user_profile.has_routine(p))


class TestProfileBlock(unittest.TestCase):
    def test_empty_profile_signals_none_on_file(self):
        block = ai_brain._profile_block({"name": "Asha", "timezone": "UTC"})
        self.assertIn("NONE ON FILE", block)

    def test_set_routine_is_rendered_not_none(self):
        block = ai_brain._profile_block({
            "name": "Asha", "timezone": "UTC",
            "wake_time": "06:00", "sleep_time": "22:00",
            "gym": {"default_time": "18:00", "duration_minutes": 45, "days": ["Mon", "Wed"]},
            "trading": {},
        })
        self.assertNotIn("NONE ON FILE", block)
        self.assertIn("18:00", block)
        self.assertIn("06:00", block)

    def test_prompt_clock_and_dates_use_tenant_profile_timezone(self):
        instant = dt.datetime(2026, 7, 18, 23, 30, tzinfo=dt.timezone.utc)
        india_now = ai_brain._profile_now(
            {"timezone": "Asia/Kolkata"},
            now_utc=instant,
        )
        la_now = ai_brain._profile_now(
            {"timezone": "America/Los_Angeles"},
            now_utc=instant,
        )

        self.assertEqual(
            india_now.strftime("%Y-%m-%d %H:%M %Z"),
            "2026-07-19 05:00 IST",
        )
        self.assertEqual(
            la_now.strftime("%Y-%m-%d %H:%M %Z"),
            "2026-07-18 16:30 PDT",
        )
        self.assertIn(
            "Sunday = 2026-07-19  (today)",
            ai_brain._upcoming_dates_table(india_now),
        )
        self.assertIn(
            "Saturday = 2026-07-18  (today)",
            ai_brain._upcoming_dates_table(la_now),
        )


if __name__ == "__main__":
    unittest.main()
