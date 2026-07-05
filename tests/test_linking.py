"""
test_linking.py — identity unification (Phase 2 step 1).

link_identities() folds a secondary person into a primary: re-points platform
identities, moves summary/customer-profile, writes a tombstone alias, deletes the
empty secondary. canonical_person_id() follows the tombstone.

Run:  ./venv/bin/python -m unittest tests.test_linking -v
"""

import datetime as dt
import unittest
import uuid

from services import db, state_store
from services.identity import (
    canonical_person_id,
    get_person,
    link_identities,
    list_platform_identities_for_person,
    resolve,
)
from services.identity.store import connect
from services.identity.summaries import get_summary_md
from services.tenancy import tenant_context
from services.config import settings


def _tc():
    return tenant_context(settings.default_tenant_id)


class TestLinkIdentities(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.bootstrap()

    def _two_people(self):
        # Unique ids per call so the test is isolated from any prior run's data.
        sfx = uuid.uuid4().hex[:10]
        with _tc():
            tg = resolve(platform="telegram", platform_user_id=f"tg_{sfx}", display_name="Asha TG")
            dc = resolve(platform="discord", platform_user_id=f"dc_{sfx}", display_name="Asha DC")
        return tg, dc, f"dc_{sfx}"

    def test_repoints_identities_and_deletes_secondary(self):
        primary, secondary, dc_uid = self._two_people()
        self.assertNotEqual(primary, secondary)
        with _tc():
            res = link_identities(primary, secondary)
            self.assertTrue(res["linked"])
            self.assertEqual(res["platform_identities"], 1)
            # secondary gone, both identities now under primary
            self.assertIsNone(get_person(secondary))
            ids = list_platform_identities_for_person(primary)
            platforms = sorted(i.platform for i in ids)
            self.assertEqual(platforms, ["discord", "telegram"])
            # future resolve of the secondary's platform returns the primary
            again = resolve(platform="discord", platform_user_id=dc_uid)
            self.assertEqual(again, primary)

    def test_canonical_person_id_follows_alias(self):
        primary, secondary, _ = self._two_people()
        with _tc():
            link_identities(primary, secondary)
            self.assertEqual(canonical_person_id(secondary), primary)
            self.assertEqual(canonical_person_id(primary), primary)  # no alias → itself

    def test_self_link_is_noop(self):
        primary, _, _ = self._two_people()
        with _tc():
            res = link_identities(primary, primary)
        self.assertFalse(res["linked"])

    def test_missing_secondary_raises(self):
        primary, _, _ = self._two_people()
        with _tc():
            with self.assertRaises(ValueError):
                link_identities(primary, "pers_does_not_exist")

    def test_summary_moves_when_primary_has_none(self):
        primary, secondary, _ = self._two_people()
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        with _tc():
            with connect() as conn:
                conn.execute(
                    "INSERT INTO person_summaries (person_id, summary_md, last_built_at, source_message_count) "
                    "VALUES (?, ?, ?, 0)",
                    (secondary, "remembers gym at 6pm", now),
                )
            res = link_identities(primary, secondary)
            self.assertTrue(res["summary_moved"])
            self.assertEqual(get_summary_md(primary), "remembers gym at 6pm")

    def test_customer_profile_moves_when_primary_has_none(self):
        primary, secondary, _ = self._two_people()
        with _tc():
            state_store.write_json("customers", secondary, {"person_id": secondary, "status": "active", "name": "Asha"})
            res = link_identities(primary, secondary)
            self.assertTrue(res["customer_profile_moved"])
            moved = state_store.read_json("customers", primary, default=None)
            self.assertIsNotNone(moved)
            self.assertEqual(moved["person_id"], primary)
            self.assertEqual(moved["status"], "active")


    def test_history_follows_merged_person(self):
        from services.identity import history
        primary, secondary, _ = self._two_people()
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        with _tc():
            state_store.append_event(
                history.MEMORY_NAMESPACE, history.CONVERSATIONS_KEY,
                {"timestamp": now, "role": "user", "text": "secret from discord",
                 "metadata": {"person_id": secondary}},
            )
            # Before linking, the primary doesn't see the secondary's history.
            before = history.recent_for_person(primary)
            self.assertFalse(any(e.get("text") == "secret from discord" for e in before))
            # After linking, it does.
            link_identities(primary, secondary)
            after = history.recent_for_person(primary)
            self.assertTrue(any(e.get("text") == "secret from discord" for e in after))


if __name__ == "__main__":
    unittest.main()
