"""
test_web_actions.py — surface-agnostic action executor for the web chat.

Verifies routing (conversational actions return None so the caller uses the
brain's reply), a real read action (trading rules), a write action (add_task),
and the graceful "calendar not connected" path. Service calls are stubbed at the
module boundary — web_actions imports them lazily, so patching the module attr
is enough. No network, no DB.

Run:  ./venv/bin/python -m unittest tests.test_web_actions -v
"""

import unittest
from unittest import mock

from services import web_actions
import services.user_profile as user_profile


class WebActionsTest(unittest.TestCase):
    def setUp(self):
        # A predictable profile without touching the DB.
        self._patch = mock.patch.object(
            user_profile, "load_profile",
            return_value={"timezone": "Asia/Kolkata", "trading": {"rules": ["No revenge trading"]}},
        )
        self._patch.start()

    def tearDown(self):
        self._patch.stop()

    def test_conversational_action_is_unhandled(self):
        self.assertIsNone(web_actions.execute("chat", {}))
        self.assertIsNone(web_actions.execute("something_new", {}))

    def test_show_trading_rules(self):
        out = web_actions.execute("show_trading_rules", {})
        self.assertIn("No revenge trading", out)

    def test_add_task_routes_to_tracker(self):
        import services.task_tracker as tt
        with mock.patch.object(tt, "add_task", return_value={"task": "gym"}) as m:
            out = web_actions.execute("add_task", {"task": "gym"})
        m.assert_called_once()
        self.assertIn("gym", out)

    def test_calendar_action_without_connection_prompts_connect(self):
        import calendars.unified as unified

        class _NoCal:
            google = None
            outlook = None

        with mock.patch.object(unified, "UnifiedCalendar", _NoCal):
            out = web_actions.execute("show_schedule", {})
        self.assertIn("isn't connected", out)

    def test_handler_never_raises(self):
        # A calendar action whose params are malformed still returns a message.
        import calendars.unified as unified

        class _Cal:
            google = object()
            outlook = None

            def format_events(self, *_):
                return "x"

        with mock.patch.object(unified, "UnifiedCalendar", _Cal):
            out = web_actions.execute("show_date", {"date": "not-a-date"})
        self.assertIsInstance(out, str)


if __name__ == "__main__":
    unittest.main()
