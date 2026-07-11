"""
test_skills.py — declarative skill packs (Feature 6).

Covers registry projection (active packs contribute the action contract),
per-pack flag gating (disabling a pack removes its actions from the prompt AND
from execution), action ownership, and a regression guard that every action the
brain can emit is owned by exactly one pack. Stdlib unittest with an in-memory
state_store fake for the flag store.

Run:  ./venv/bin/python -m unittest tests.test_skills -v
"""

import unittest

from services import skills
from services.skills import registry


# The complete set of actions the brain may emit — the contract the handler
# dispatch chain in bot/handlers/messages.py implements. If a capability is
# added, it must land in a pack (and this set updated), or the regression test
# below fails.
ALL_ACTIONS = {
    "chat",
    "add_task", "mark_done", "show_tasks",
    "show_schedule", "show_tomorrow", "show_date", "check_conflicts",
    "move_event", "create_event", "create_recurring_events", "delete_event",
    "show_trading_rules", "add_trading_rule",
    "show_briefing",
    "set_reminder", "set_reminders", "show_reminders",
    "update_profile",
    "send_platform_message",
    "search_memory", "show_decisions",
    "show_calendars",
    "check_emails", "show_email_prefs",
    "summarize_file", "attach_file_to_event", "send_file", "upload_to_drive",
}


class _FakeStore:
    def __init__(self):
        self.json = {}

    def read_json(self, ns, key, default=None):
        return self.json.get((ns, key), default)

    def write_json(self, ns, key, value):
        self.json[(ns, key)] = value


class _SkillsBase(unittest.TestCase):
    def setUp(self):
        self.store = _FakeStore()
        self._orig = registry.state_store
        registry.state_store = self.store

    def tearDown(self):
        registry.state_store = self._orig


class RegistryTest(_SkillsBase):
    def test_every_action_is_owned_by_a_pack(self):
        owned = set()
        for s in skills.all_skills():
            owned |= set(s.actions)
        self.assertEqual(owned, ALL_ACTIONS)

    def test_no_action_owned_by_two_packs(self):
        seen = {}
        for s in skills.all_skills():
            for a in s.actions:
                self.assertNotIn(a, seen, f"{a} owned by both {seen.get(a)} and {s.id}")
                seen[a] = s.id

    def test_packs_projected_in_order(self):
        orders = [s.order for s in skills.all_skills()]
        self.assertEqual(orders, sorted(orders))


class ProjectionTest(_SkillsBase):
    def test_all_actions_present_when_all_packs_enabled(self):
        contract = skills.build_action_contract()
        for action in ALL_ACTIONS:
            self.assertIn(f'"{action}"', contract, f"{action} missing from projected contract")

    def test_action_descriptions_preserved(self):
        contract = skills.build_action_contract()
        # Spot-check that the descriptive text travelled with the action.
        self.assertIn("full daily briefing", contract)
        self.assertIn("create a SERIES of events", contract)
        self.assertIn("FILE + EVENT ROUTING", contract)


class FlagGatingTest(_SkillsBase):
    def test_disabling_a_pack_removes_its_actions(self):
        self.assertTrue(skills.is_action_enabled("check_emails"))
        registry.set_flag_enabled("email", False)

        self.assertFalse(skills.is_action_enabled("check_emails"))
        self.assertFalse(skills.is_action_enabled("show_email_prefs"))

        contract = skills.build_action_contract()
        self.assertNotIn('"check_emails"', contract)
        self.assertNotIn('"show_email_prefs"', contract)
        # Other packs are untouched.
        self.assertIn('"show_briefing"', contract)

    def test_re_enabling_restores_the_pack(self):
        registry.set_flag_enabled("trading", False)
        self.assertFalse(skills.is_action_enabled("add_trading_rule"))
        registry.set_flag_enabled("trading", True)
        self.assertTrue(skills.is_action_enabled("add_trading_rule"))
        self.assertIn('"add_trading_rule"', skills.build_action_contract())

    def test_core_pack_cannot_be_disabled(self):
        registry.set_flag_enabled("core", False)  # try to switch off chat
        self.assertTrue(skills.is_action_enabled("chat"))
        self.assertIn('"chat"', skills.build_action_contract())

    def test_unowned_action_is_always_allowed(self):
        # Legacy / not-yet-migrated actions aren't constrained by the gate.
        self.assertTrue(skills.is_action_enabled("some_future_action"))

    def test_owner_of_resolves_pack(self):
        self.assertEqual(skills.owner_of("create_event").id, "calendar")
        self.assertEqual(skills.owner_of("check_emails").id, "email")
        self.assertIsNone(skills.owner_of("nonexistent"))


class AiBrainAssemblyTest(_SkillsBase):
    def test_brain_contract_includes_preamble_projection_and_rules(self):
        from services import ai_brain

        contract = ai_brain._build_action_contract()
        self.assertIn("WHO YOU'RE TALKING TO", contract)      # preamble
        self.assertIn("Available actions:", contract)          # projection header
        self.assertIn('"create_event"', contract)              # a projected action
        self.assertIn("Be smart about interpreting intent", contract)  # rules
        self.assertIn("NEVER CLAIM YOU CREATED MULTIPLE EVENTS", contract)  # critical rule


if __name__ == "__main__":
    unittest.main()
