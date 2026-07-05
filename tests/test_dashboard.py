"""
test_dashboard.py — dashboard skeleton (Phase 2, build-order step 3).

Covers the testable units without a live HTTP server: the overview data
assembly, the magic-link token round-trip, and session-cookie parsing.

Run:  ./venv/bin/python -m unittest tests.test_dashboard -v
"""

import unittest
import uuid
from types import SimpleNamespace

from services import db
from services.identity import resolve
from services.tenancy import tenant_context
from services.config import settings
from services.onboarding import links
from services import dashboard  # framework-free service layer


def _tc():
    return tenant_context(settings.default_tenant_id)


class TestDashboard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.bootstrap()

    def test_overview_lists_connected_platforms(self):
        sfx = uuid.uuid4().hex[:10]
        with _tc():
            pid = resolve(platform="telegram", platform_user_id=f"tg_{sfx}", display_name="Asha")
        data = dashboard.overview(pid, settings.default_tenant_id)
        self.assertEqual(data["name"], "Asha")
        self.assertTrue(any(p["platform"] == "telegram" for p in data["platforms"]))
        self.assertIn("conversation_count", data)

    def test_magic_link_token_round_trip(self):
        link = dashboard.make_dashboard_link("pers_abc123", settings.default_tenant_id)
        self.assertIn("/dashboard/login?token=", link)
        token = link.split("token=", 1)[1]
        payload = links.verify_token(token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["pid"], "pers_abc123")

    def test_session_reads_valid_cookie_and_rejects_garbage(self):
        tok = dashboard.make_session_token("pers_xyz", settings.default_tenant_id)
        self.assertEqual(dashboard.session_from_token(tok)["pid"], "pers_xyz")
        self.assertIsNone(dashboard.session_from_token(None))
        self.assertIsNone(dashboard.session_from_token("garbage.token"))


if __name__ == "__main__":
    unittest.main()
