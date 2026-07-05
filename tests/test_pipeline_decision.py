"""
test_pipeline_decision.py — Lock the pure Decision mapper.

``decision_from_action`` maps a resolver EffectiveAction to the pipeline
Decision the adapters act on. It's pure (no DB), so it's table-tested here.

Run:  ./venv/bin/python -m unittest tests.test_pipeline_decision -v
"""

import unittest

from services.directives.resolve import EffectiveAction
from services.directives.store import (
    ACTION_AUTO_REPLY,
    ACTION_IGNORE,
    ACTION_PRIORITIZE,
    ACTION_REPLY,
)
from services.platforms.base import (
    ACT_AUTO_REPLY,
    ACT_IGNORE,
    ACT_PRIORITIZE,
    ACT_REPLY,
    decision_from_action,
)

PERSON = "pers_x"


class TestDecisionMapper(unittest.TestCase):
    def test_default_reply(self):
        d = decision_from_action(EffectiveAction(action=ACTION_REPLY), PERSON)
        self.assertEqual(d.action, ACT_REPLY)
        self.assertTrue(d.should_reply)
        self.assertFalse(d.is_silenced)
        self.assertEqual(d.person_id, PERSON)

    def test_ignore_is_hard_stop(self):
        d = decision_from_action(
            EffectiveAction(action=ACTION_IGNORE, chosen_directive_id="dir_1"), PERSON,
        )
        self.assertEqual(d.action, ACT_IGNORE)
        self.assertTrue(d.is_silenced)
        self.assertFalse(d.should_reply)
        self.assertEqual(d.directive_id, "dir_1")

    def test_auto_reply_with_text(self):
        d = decision_from_action(
            EffectiveAction(action=ACTION_AUTO_REPLY, payload={"text": "  brb  "}), PERSON,
        )
        self.assertEqual(d.action, ACT_AUTO_REPLY)
        self.assertEqual(d.canned_text, "brb")
        self.assertFalse(d.should_reply)

    def test_auto_reply_without_text_falls_back_to_reply(self):
        # A malformed auto_reply must never wedge a user into silence.
        d = decision_from_action(EffectiveAction(action=ACTION_AUTO_REPLY, payload={}), PERSON)
        self.assertEqual(d.action, ACT_REPLY)
        self.assertTrue(d.should_reply)

    def test_prioritize_replies_with_soft_hint(self):
        d = decision_from_action(EffectiveAction(action=ACTION_PRIORITIZE), PERSON)
        self.assertEqual(d.action, ACT_PRIORITIZE)
        self.assertTrue(d.should_reply)
        self.assertTrue(d.soft_hints)  # composer gets a hint


if __name__ == "__main__":
    unittest.main()
