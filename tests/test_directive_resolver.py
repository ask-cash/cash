"""
test_directive_resolver.py — Lock the conflict resolver's behavior.

The resolver is a PURE function on (event, directives) -> EffectiveAction, so it
needs no DB and no mocks. The design doc (§11) flags this as the one thing that
must have regression tests before trusting it; this file is that matrix.

Run:  ./venv/bin/python -m unittest tests.test_directive_resolver -v
"""

import datetime as dt
import json
import unittest

from services.directives.resolve import Event, effective_action
from services.directives.store import (
    ACTION_AUTO_REPLY,
    ACTION_IGNORE,
    ACTION_PRIORITIZE,
    ACTION_REPLY,
    Directive,
)

PERSON = "pers_alice"
OTHER = "pers_bob"
NOW = dt.datetime(2026, 6, 26, 12, 0, 0, tzinfo=dt.timezone.utc)


def _ts(offset_minutes: int = 0) -> str:
    return (NOW + dt.timedelta(minutes=offset_minutes)).isoformat()


def make_directive(
    action,
    *,
    target=PERSON,
    platform="*",
    workspace="*",
    channel="*",
    created_offset=0,
    expires_at=None,
    revoked_at=None,
    payload=None,
    directive_id=None,
):
    return Directive(
        directive_id=directive_id or f"dir_{action}_{created_offset}",
        issued_by="suhail",
        action=action,
        target_person_id=target,
        scope_platform=platform,
        scope_workspace=workspace,
        scope_channel=channel,
        payload_json=json.dumps(payload) if payload else None,
        expires_at=expires_at,
        source_text=None,
        created_at=_ts(created_offset),
        revoked_at=revoked_at,
    )


def discord_event(channel="chan-1", workspace="guild-1", person=PERSON):
    return Event(platform="discord", workspace_id=workspace, channel_id=channel, person_id=person)


class TestNoDirectives(unittest.TestCase):
    def test_empty_set_defaults_to_reply(self):
        out = effective_action(discord_event(), [], now=NOW)
        self.assertEqual(out.action, ACTION_REPLY)
        self.assertTrue(out.is_default)

    def test_directive_for_other_person_is_ignored(self):
        d = make_directive(ACTION_IGNORE, target=OTHER)
        out = effective_action(discord_event(person=PERSON), [d], now=NOW)
        self.assertEqual(out.action, ACTION_REPLY)


class TestHardActionPrecedence(unittest.TestCase):
    def test_ignore_plus_prioritize_same_scope_ignore_wins(self):
        # Design doc §11 matrix: ignore + prioritize same person -> ignore wins.
        # Order-independent: prioritize is newer, but ignore still wins on the
        # hard-action tiebreak at equal specificity.
        prioritize = make_directive(ACTION_PRIORITIZE, created_offset=10)
        ignore = make_directive(ACTION_IGNORE, created_offset=0)
        out = effective_action(discord_event(), [prioritize, ignore], now=NOW)
        self.assertEqual(out.action, ACTION_IGNORE)

    def test_expired_ignore_plus_active_prioritize_prioritize_wins(self):
        # Design doc §11 matrix: expired ignore + active prioritize -> prioritize.
        expired_ignore = make_directive(ACTION_IGNORE, expires_at=_ts(-5))
        prioritize = make_directive(ACTION_PRIORITIZE)
        out = effective_action(discord_event(), [expired_ignore, prioritize], now=NOW)
        self.assertEqual(out.action, ACTION_PRIORITIZE)

    def test_revoked_directive_is_inert(self):
        revoked = make_directive(ACTION_IGNORE, revoked_at=_ts(-1))
        out = effective_action(discord_event(), [revoked], now=NOW)
        self.assertEqual(out.action, ACTION_REPLY)


class TestScopeMatching(unittest.TestCase):
    def test_channel_scoped_ignore_does_not_fire_in_other_channel(self):
        # Design doc §11 matrix: channel-scoped ignore but message elsewhere -> no effect.
        d = make_directive(ACTION_IGNORE, channel="trading-room")
        out = effective_action(discord_event(channel="random"), [d], now=NOW)
        self.assertEqual(out.action, ACTION_REPLY)

    def test_channel_scoped_ignore_fires_in_its_channel(self):
        d = make_directive(ACTION_IGNORE, channel="trading-room")
        out = effective_action(discord_event(channel="trading-room"), [d], now=NOW)
        self.assertEqual(out.action, ACTION_IGNORE)

    def test_platform_scoped_directive_does_not_fire_on_other_platform(self):
        d = make_directive(ACTION_IGNORE, platform="slack")
        out = effective_action(discord_event(), [d], now=NOW)
        self.assertEqual(out.action, ACTION_REPLY)


class TestSpecificity(unittest.TestCase):
    def test_narrow_auto_reply_beats_global_ignore(self):
        # More-specific scope wins over the hard-action preference.
        global_ignore = make_directive(ACTION_IGNORE)
        channel_auto = make_directive(
            ACTION_AUTO_REPLY, channel="chan-1", payload={"text": "brb"},
        )
        out = effective_action(discord_event(channel="chan-1"), [global_ignore, channel_auto], now=NOW)
        self.assertEqual(out.action, ACTION_AUTO_REPLY)
        self.assertEqual(out.payload.get("text"), "brb")

    def test_target_specific_beats_scope_only(self):
        scope_only = make_directive(ACTION_IGNORE, target=None)  # everyone in scope
        targeted = make_directive(ACTION_PRIORITIZE, target=PERSON)
        out = effective_action(discord_event(), [scope_only, targeted], now=NOW)
        self.assertEqual(out.action, ACTION_PRIORITIZE)


class TestTiebreakByRecency(unittest.TestCase):
    def test_newer_same_action_same_scope_wins(self):
        old = make_directive(ACTION_AUTO_REPLY, created_offset=0,
                             payload={"text": "old"}, directive_id="dir_old")
        new = make_directive(ACTION_AUTO_REPLY, created_offset=10,
                             payload={"text": "new"}, directive_id="dir_new")
        out = effective_action(discord_event(), [old, new], now=NOW)
        self.assertEqual(out.chosen_directive_id, "dir_new")
        self.assertEqual(out.payload.get("text"), "new")


class TestScopeOnlyDirectives(unittest.TestCase):
    def test_scope_only_applies_to_everyone_in_scope(self):
        d = make_directive(ACTION_IGNORE, target=None, channel="spam")
        out = effective_action(discord_event(channel="spam", person=OTHER), [d], now=NOW)
        self.assertEqual(out.action, ACTION_IGNORE)


if __name__ == "__main__":
    unittest.main()
