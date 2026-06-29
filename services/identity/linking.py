"""
linking.py — Merge two persons into one (cross-platform identity unification).

Phase 2 of cash-cross-platform-presence.md. ``people.resolve()`` deliberately
mints a new ``person_id`` per platform account; this module is the explicit,
auditable way to declare "these two persons are the same human" and fold their
data together so memory follows them across platforms.

``link_identities(primary, secondary)``:
  - re-points the secondary's platform_identities onto the primary,
  - re-points directives that targeted the secondary,
  - moves the secondary's rolling summary (only if the primary has none — summaries
    regenerate, so a clash just drops the secondary's),
  - moves the secondary's CustomerProfile (only if the primary has none),
  - records a tombstone alias (secondary → primary) for audit + later lookup,
  - deletes the now-empty secondary person row.

It is **additive and safe**: validates inputs, no-ops on a self-link, and never
touches the inbound hot path. ``canonical_person_id()`` follows the tombstones so
any lingering reference to a merged id resolves to the survivor.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Optional

from services import state_store
from services.identity.store import connect

logger = logging.getLogger(__name__)

# onboarding.profiles stores CustomerProfile under this kv namespace, keyed by person_id.
_CUSTOMERS_NS = "customers"


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def canonical_person_id(person_id: str) -> str:
    """Follow alias tombstones to the surviving person id (1 hop is typical).

    Cycle-guarded. Returns the input unchanged if there's no alias for it.
    """
    if not person_id:
        return person_id
    seen: set[str] = set()
    cur = person_id
    with connect() as conn:
        while cur and cur not in seen:
            seen.add(cur)
            row = conn.execute(
                "SELECT canonical_person_id FROM person_aliases WHERE alias_person_id = ?",
                (cur,),
            ).fetchone()
            if row is None:
                return cur
            cur = row["canonical_person_id"]
    return cur


def merged_into(person_id: str) -> set[str]:
    """All person_ids that were merged INTO ``person_id`` (transitively).

    Reverse of the tombstone edges: if A→P and B→A, ``merged_into(P)`` is {A, B}.
    Used so a survivor inherits the raw conversation history of everyone folded
    into it. Returns an empty set when nothing was merged.
    """
    if not person_id:
        return set()
    result: set[str] = set()
    frontier = [person_id]
    with connect() as conn:
        while frontier:
            cur = frontier.pop()
            rows = conn.execute(
                "SELECT alias_person_id FROM person_aliases WHERE canonical_person_id = ?",
                (cur,),
            ).fetchall()
            for r in rows:
                alias = r["alias_person_id"]
                if alias not in result:
                    result.add(alias)
                    frontier.append(alias)
    return result


def _merge_customer_profile(primary: str, secondary: str) -> bool:
    """Move the secondary's CustomerProfile to the primary if the primary has none.

    Best-effort: never raises (linking should not fail because the kv read hiccuped).
    Returns True if a profile was moved.
    """
    try:
        sec = state_store.read_json(_CUSTOMERS_NS, secondary, default=None)
        if not isinstance(sec, dict) or not sec:
            return False
        prim = state_store.read_json(_CUSTOMERS_NS, primary, default=None)
        if isinstance(prim, dict) and prim:
            return False  # primary already onboarded — keep theirs
        sec["person_id"] = primary
        state_store.write_json(_CUSTOMERS_NS, primary, sec)
        return True
    except Exception:
        logger.exception("[linking] customer-profile merge failed %s → %s", secondary, primary)
        return False


def link_identities(primary_person_id: str, secondary_person_id: str) -> dict:
    """Fold ``secondary_person_id`` into ``primary_person_id``. Returns a summary dict.

    Raises ValueError on missing ids. No-ops (linked=False) on a self-link.
    """
    if not primary_person_id or not secondary_person_id:
        raise ValueError("both primary_person_id and secondary_person_id are required")
    if primary_person_id == secondary_person_id:
        return {"linked": False, "reason": "same person"}

    result = {
        "linked": True,
        "primary": primary_person_id,
        "secondary": secondary_person_id,
        "platform_identities": 0,
        "directives": 0,
        "summary_moved": False,
    }

    with connect() as conn:
        if conn.execute(
            "SELECT 1 FROM people WHERE person_id = ?", (primary_person_id,)
        ).fetchone() is None:
            raise ValueError(f"primary {primary_person_id!r} does not exist")
        if conn.execute(
            "SELECT 1 FROM people WHERE person_id = ?", (secondary_person_id,)
        ).fetchone() is None:
            raise ValueError(f"secondary {secondary_person_id!r} does not exist")

        # Count before update (engine-agnostic — don't rely on cursor.rowcount).
        result["platform_identities"] = conn.execute(
            "SELECT COUNT(*) FROM platform_identities WHERE person_id = ?",
            (secondary_person_id,),
        ).fetchone()[0]
        conn.execute(
            "UPDATE platform_identities SET person_id = ? WHERE person_id = ?",
            (primary_person_id, secondary_person_id),
        )

        result["directives"] = conn.execute(
            "SELECT COUNT(*) FROM directives WHERE target_person_id = ?",
            (secondary_person_id,),
        ).fetchone()[0]
        conn.execute(
            "UPDATE directives SET target_person_id = ? WHERE target_person_id = ?",
            (primary_person_id, secondary_person_id),
        )

        # person_summaries PK is (tenant_id, person_id): move only if primary has none.
        sec_sum = conn.execute(
            "SELECT 1 FROM person_summaries WHERE person_id = ?", (secondary_person_id,)
        ).fetchone()
        if sec_sum is not None:
            prim_sum = conn.execute(
                "SELECT 1 FROM person_summaries WHERE person_id = ?", (primary_person_id,)
            ).fetchone()
            if prim_sum is not None:
                conn.execute(
                    "DELETE FROM person_summaries WHERE person_id = ?", (secondary_person_id,)
                )
            else:
                conn.execute(
                    "UPDATE person_summaries SET person_id = ? WHERE person_id = ?",
                    (primary_person_id, secondary_person_id),
                )
                result["summary_moved"] = True

        # Tombstone: secondary → primary (audit + canonical_person_id lookups).
        conn.execute(
            """
            INSERT INTO person_aliases (alias_person_id, canonical_person_id, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT (tenant_id, alias_person_id)
            DO UPDATE SET canonical_person_id = excluded.canonical_person_id
            """,
            (secondary_person_id, primary_person_id, _now_iso()),
        )

        # The secondary person is now empty — remove it.
        conn.execute("DELETE FROM people WHERE person_id = ?", (secondary_person_id,))

    result["customer_profile_moved"] = _merge_customer_profile(primary_person_id, secondary_person_id)

    logger.info(
        "[linking] merged %s → %s: %d identities, %d directives, summary_moved=%s, profile_moved=%s",
        secondary_person_id, primary_person_id,
        result["platform_identities"], result["directives"],
        result["summary_moved"], result["customer_profile_moved"],
    )
    return result
