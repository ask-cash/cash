"""
people.py — Person + PlatformIdentity API.

The single hot path is `resolve()`: given a (platform, workspace_id, platform_user_id),
return the canonical `person_id`, auto-creating both rows on first sight and
updating last_seen / display_name / handle on every subsequent call.

Platform-aware workspace normalization
--------------------------------------
- Discord and Telegram have GLOBAL user IDs (a snowflake / user id is unique
  across all guilds and chats). We store workspace_id='' for these so the
  same human in two guilds maps to ONE person_id.
- Slack and Teams have WORKSPACE-SCOPED user IDs (the same `U03ABC` may exist
  in two unrelated Slack workspaces and refer to two different humans). We
  preserve the actual workspace_id for these.

This is enforced here, in the application layer, so the schema's
UNIQUE(platform, workspace_id, platform_user_id) constraint does the right
thing for both classes of platform.
"""

import datetime as dt
import logging
import secrets
from dataclasses import dataclass
from typing import Optional

from services.db import from_row
from services.identity.store import connect

logger = logging.getLogger(__name__)

PERSON_ID_PREFIX = "pers_"
PLATFORM_IDENTITY_ID_PREFIX = "pi_"

# Platforms whose platform_user_id is globally unique. workspace_id is
# normalized to '' for these so cross-workspace activity merges into one person.
_GLOBAL_USER_ID_PLATFORMS = {"discord", "telegram"}


@dataclass
class Person:
    person_id: str
    canonical_name: Optional[str]
    notes: Optional[str]
    preferences_json: Optional[str]
    created_at: str
    updated_at: str


@dataclass
class PlatformIdentity:
    platform_identity_id: str
    person_id: str
    platform: str
    workspace_id: str
    platform_user_id: str
    display_name: Optional[str]
    handle: Optional[str]
    first_seen: str
    last_seen: str


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _normalize_workspace(platform: str, workspace_id: Optional[str]) -> str:
    if platform in _GLOBAL_USER_ID_PLATFORMS:
        return ""
    return (workspace_id or "").strip()


def _new_person_id() -> str:
    return PERSON_ID_PREFIX + secrets.token_hex(6)


def _new_platform_identity_id() -> str:
    return PLATFORM_IDENTITY_ID_PREFIX + secrets.token_hex(6)


def resolve(
    *,
    platform: str,
    platform_user_id: str,
    workspace_id: Optional[str] = None,
    display_name: Optional[str] = None,
    handle: Optional[str] = None,
) -> str:
    """Return the person_id for this platform identity. Auto-creates on first sight.

    On repeat calls, updates last_seen and (if provided) display_name / handle —
    so renames flow through naturally without needing manual sync.
    """
    if not platform or not platform_user_id:
        raise ValueError("platform and platform_user_id are required")

    norm_workspace = _normalize_workspace(platform, workspace_id)
    pu_id = str(platform_user_id)
    now = _now_iso()

    with connect() as conn:
        row = conn.execute(
            """
            SELECT platform_identity_id, person_id
              FROM platform_identities
             WHERE platform = ? AND workspace_id = ? AND platform_user_id = ?
            """,
            (platform, norm_workspace, pu_id),
        ).fetchone()

        if row is not None:
            conn.execute(
                """
                UPDATE platform_identities
                   SET last_seen     = ?,
                       display_name  = COALESCE(?, display_name),
                       handle        = COALESCE(?, handle)
                 WHERE platform_identity_id = ?
                """,
                (now, display_name, handle, row["platform_identity_id"]),
            )
            return row["person_id"]

        person_id = _new_person_id()
        canonical_name = display_name or handle or pu_id
        conn.execute(
            """
            INSERT INTO people (person_id, canonical_name, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (person_id, canonical_name, now, now),
        )
        conn.execute(
            """
            INSERT INTO platform_identities (
                platform_identity_id, person_id, platform, workspace_id,
                platform_user_id, display_name, handle, first_seen, last_seen
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _new_platform_identity_id(),
                person_id, platform, norm_workspace, pu_id,
                display_name, handle, now, now,
            ),
        )
        logger.info(
            "[identity] created person=%s for platform=%s workspace=%r user_id=%s name=%r",
            person_id, platform, norm_workspace, pu_id, display_name or handle,
        )
        return person_id


def get_person(person_id: str) -> Optional[Person]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM people WHERE person_id = ?", (person_id,)
        ).fetchone()
        if row is None:
            return None
        return from_row(Person, row)


def list_platform_identities_for_person(person_id: str) -> list[PlatformIdentity]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM platform_identities WHERE person_id = ? ORDER BY first_seen",
            (person_id,),
        ).fetchall()
    return [from_row(PlatformIdentity, r) for r in rows]


def find_platform_identity(
    platform: str,
    platform_user_id: str,
    *,
    workspace_id: Optional[str] = None,
) -> Optional[PlatformIdentity]:
    """Look up an existing platform identity. Does NOT auto-create.

    Use this when you only want to know "do we have a record for this user?"
    — typically from slash commands where auto-creating an empty person on a
    typo would be wrong. Use resolve() when you actively want to record a
    new sighting.
    """
    norm_workspace = _normalize_workspace(platform, workspace_id)
    pu_id = str(platform_user_id)
    with connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM platform_identities
             WHERE platform = ? AND workspace_id = ? AND platform_user_id = ?
            """,
            (platform, norm_workspace, pu_id),
        ).fetchone()
    return from_row(PlatformIdentity, row) if row else None


def find_by_hint(hint: str, *, platform: Optional[str] = None) -> list[Person]:
    """Resolve a free-text hint (display name, @handle, or person_id) to people.

    Exact match only — case-insensitive on names/handles, exact on person_id.
    Returns all matching persons; the caller disambiguates if more than one.
    Substring matching is intentionally *not* supported here — that's how the
    pre-Step-3 system kept colliding on common names. Be specific or be told
    to be more specific.

    If `platform` is given, restrict to people who have at least one identity
    on that platform.
    """
    if not hint:
        return []
    cleaned = hint.strip().lstrip("@")
    if not cleaned:
        return []

    # Direct person_id lookup — power users / scripts.
    if cleaned.startswith(PERSON_ID_PREFIX):
        p = get_person(cleaned)
        return [p] if p else []

    needle = cleaned.lower()

    with connect() as conn:
        if platform:
            rows = conn.execute(
                """
                SELECT DISTINCT p.* FROM people p
                  JOIN platform_identities pi ON pi.person_id = p.person_id
                 WHERE pi.platform = ?
                   AND (
                        LOWER(COALESCE(p.canonical_name, '')) = ?
                     OR LOWER(COALESCE(pi.display_name, '')) = ?
                     OR LOWER(COALESCE(pi.handle, ''))       = ?
                   )
                """,
                (platform, needle, needle, needle),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT DISTINCT p.* FROM people p
                  LEFT JOIN platform_identities pi ON pi.person_id = p.person_id
                 WHERE LOWER(COALESCE(p.canonical_name, '')) = ?
                    OR LOWER(COALESCE(pi.display_name, '')) = ?
                    OR LOWER(COALESCE(pi.handle, ''))       = ?
                """,
                (needle, needle, needle),
            ).fetchall()
    return [from_row(Person, r) for r in rows]


def set_canonical_name(person_id: str, name: str) -> None:
    """Update the canonical_name on an existing person."""
    with connect() as conn:
        conn.execute(
            "UPDATE people SET canonical_name = ?, updated_at = ? WHERE person_id = ?",
            (name, _now_iso(), person_id),
        )


def link_platform_identity(
    *,
    person_id: str,
    platform: str,
    platform_user_id: str,
    workspace_id: Optional[str] = None,
    display_name: Optional[str] = None,
    handle: Optional[str] = None,
) -> str:
    """Attach a platform identity to an EXISTING person. Returns platform_identity_id.

    Idempotent. If the (platform, workspace, platform_user_id) row already exists
    pointing at a different person, that row is re-pointed to `person_id` and
    the orphaned source person is deleted if it has no remaining identities.
    This is the right thing for the backfill case where we have authoritative
    config (e.g. env vars) saying "this Discord ID is Suhail."

    Raises ValueError if person_id does not exist.
    """
    norm_workspace = _normalize_workspace(platform, workspace_id)
    pu_id = str(platform_user_id)
    now = _now_iso()

    with connect() as conn:
        target = conn.execute(
            "SELECT person_id FROM people WHERE person_id = ?", (person_id,),
        ).fetchone()
        if target is None:
            raise ValueError(f"person_id {person_id!r} does not exist")

        existing = conn.execute(
            """
            SELECT platform_identity_id, person_id
              FROM platform_identities
             WHERE platform = ? AND workspace_id = ? AND platform_user_id = ?
            """,
            (platform, norm_workspace, pu_id),
        ).fetchone()

        if existing is not None:
            old_person = existing["person_id"]
            if old_person == person_id:
                conn.execute(
                    """
                    UPDATE platform_identities
                       SET last_seen    = ?,
                           display_name = COALESCE(?, display_name),
                           handle       = COALESCE(?, handle)
                     WHERE platform_identity_id = ?
                    """,
                    (now, display_name, handle, existing["platform_identity_id"]),
                )
                return existing["platform_identity_id"]

            # Re-point to canonical person; clean up orphan if abandoned.
            conn.execute(
                """
                UPDATE platform_identities
                   SET person_id    = ?,
                       last_seen    = ?,
                       display_name = COALESCE(?, display_name),
                       handle       = COALESCE(?, handle)
                 WHERE platform_identity_id = ?
                """,
                (person_id, now, display_name, handle, existing["platform_identity_id"]),
            )
            remaining = conn.execute(
                "SELECT COUNT(*) FROM platform_identities WHERE person_id = ?",
                (old_person,),
            ).fetchone()[0]
            if remaining == 0:
                conn.execute("DELETE FROM people WHERE person_id = ?", (old_person,))
                logger.info(
                    "[identity] merged orphan person %s into %s (re-pointed %s/%s)",
                    old_person, person_id, platform, pu_id,
                )
            return existing["platform_identity_id"]

        pi_id = _new_platform_identity_id()
        conn.execute(
            """
            INSERT INTO platform_identities (
                platform_identity_id, person_id, platform, workspace_id,
                platform_user_id, display_name, handle, first_seen, last_seen
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pi_id, person_id, platform, norm_workspace, pu_id,
                display_name, handle, now, now,
            ),
        )
        logger.info(
            "[identity] linked %s/%s/%r → person %s",
            platform, pu_id, display_name or handle, person_id,
        )
        return pi_id
