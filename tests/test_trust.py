"""
test_trust.py — Security & permissions / trust rules v2 (Feature 4).

Covers: actor-role resolution (guardian/trusted/unknown), the default-deny
policy, guardian overrides, the careful-posture approval path, and the one-time
approval grant lifecycle. Stdlib unittest with an in-memory state_store fake.

Run:  ./venv/bin/python -m unittest tests.test_trust -v
"""

import unittest

from services import security, trust


class _FakeStore:
    def __init__(self):
        self.json = {}

    def read_json(self, ns, key, default=None):
        return self.json.get((ns, key), default)

    def write_json(self, ns, key, value):
        self.json[(ns, key)] = value


class _TrustBase(unittest.TestCase):
    def setUp(self):
        self.store = _FakeStore()
        self._orig = {m: m.state_store for m in (security, trust)}
        for m in (security, trust):
            m.state_store = self.store  # type: ignore[assignment]

    def tearDown(self):
        for m, orig in self._orig.items():
            m.state_store = orig


class RoleResolutionTest(_TrustBase):
    def test_owner_is_guardian(self):
        self.assertEqual(security.resolve_role(True, None), security.ROLE_GUARDIAN)

    def test_unknown_by_default(self):
        self.assertEqual(security.resolve_role(False, "p-123"), security.ROLE_UNKNOWN)

    def test_trusted_requires_explicit_grant(self):
        self.assertEqual(security.resolve_role(False, "p-9"), security.ROLE_UNKNOWN)
        security.grant_trust("p-9")
        self.assertEqual(security.resolve_role(False, "p-9"), security.ROLE_TRUSTED)
        security.revoke_trust("p-9")
        self.assertEqual(security.resolve_role(False, "p-9"), security.ROLE_UNKNOWN)


class DefaultPolicyTest(_TrustBase):
    def test_guardian_allowed_everything_by_default(self):
        for action in ("delete_event", "send_platform_message", "chat", "add_task"):
            self.assertEqual(trust.evaluate(security.ROLE_GUARDIAN, action), trust.ALLOW)

    def test_unknown_denied_everything(self):
        for action in ("chat", "show_schedule", "search_memory", "add_task"):
            self.assertEqual(trust.evaluate(security.ROLE_UNKNOWN, action), trust.DENY)

    def test_trusted_gets_only_the_small_allow_set(self):
        self.assertEqual(trust.evaluate(security.ROLE_TRUSTED, "chat"), trust.ALLOW)
        self.assertEqual(trust.evaluate(security.ROLE_TRUSTED, "delete_event"), trust.DENY)
        self.assertEqual(trust.evaluate(security.ROLE_TRUSTED, "search_memory"), trust.DENY)


class PostureTest(_TrustBase):
    def test_careful_posture_requires_approval_for_sensitive(self):
        trust.set_posture(trust.POSTURE_CAREFUL)
        self.assertEqual(trust.evaluate(security.ROLE_GUARDIAN, "delete_event"),
                         trust.REQUIRE_APPROVAL)
        # Non-sensitive stays allowed even under careful posture.
        self.assertEqual(trust.evaluate(security.ROLE_GUARDIAN, "chat"), trust.ALLOW)

    def test_full_access_posture_allows_sensitive(self):
        trust.set_posture(trust.POSTURE_FULL)
        self.assertEqual(trust.evaluate(security.ROLE_GUARDIAN, "delete_event"), trust.ALLOW)


class OverrideTest(_TrustBase):
    def test_guardian_override_wins_over_default(self):
        trust.set_rule(security.ROLE_GUARDIAN, "delete_event", trust.DENY)
        self.assertEqual(trust.evaluate(security.ROLE_GUARDIAN, "delete_event"), trust.DENY)
        trust.clear_rule(security.ROLE_GUARDIAN, "delete_event")
        self.assertEqual(trust.evaluate(security.ROLE_GUARDIAN, "delete_event"), trust.ALLOW)

    def test_override_can_grant_a_trusted_action(self):
        trust.set_rule(security.ROLE_TRUSTED, "show_schedule", trust.ALLOW)
        self.assertEqual(trust.evaluate(security.ROLE_TRUSTED, "show_schedule"), trust.ALLOW)

    def test_bad_values_rejected(self):
        with self.assertRaises(ValueError):
            trust.set_rule(security.ROLE_GUARDIAN, "x", "maybe")
        with self.assertRaises(ValueError):
            trust.set_posture("yolo")


class ApprovalLifecycleTest(_TrustBase):
    def test_require_approval_then_one_time_grant(self):
        trust.set_posture(trust.POSTURE_CAREFUL)
        action = "upload_to_drive"
        role = security.ROLE_GUARDIAN

        # First evaluation: needs approval; no grant yet.
        self.assertEqual(trust.evaluate(role, action), trust.REQUIRE_APPROVAL)
        self.assertFalse(trust.consume_grant(role, action))

        # Guardian is prompted; the handler records the pending request.
        trust.request_approval(role, action, note="put the file on drive")
        self.assertEqual(len(trust.list_pending()), 1)

        # Guardian says /approve → one-time grant created; pending cleared.
        approved = trust.approve_latest()
        self.assertEqual(approved["action"], action)
        self.assertEqual(trust.list_pending(), [])

        # The grant is spent exactly once.
        self.assertTrue(trust.consume_grant(role, action))
        self.assertFalse(trust.consume_grant(role, action))

    def test_approve_latest_with_nothing_pending(self):
        self.assertIsNone(trust.approve_latest())


if __name__ == "__main__":
    unittest.main()
