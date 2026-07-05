"""
store.py — CRUD for the `directives` table.

A directive is a structured rule. Free-text "ignore Alice on Discord till
Monday" is parsed (Step 5) into:

    Directive(
        action='ignore',
        target_person_id='pers_...',
        scope_platform='discord',
        scope_workspace='*', scope_channel='*',
        expires_at='2026-05-04T00:00:00+00:00',
        source_text='ignore Alice on Discord till Monday',
    )

Revocation is `UPDATE … SET revoked_at = now()`. Time-bounded directives
auto-clear via expire_due() — call it from a daily scheduler job (Step 7).
"""

import datetime as dt
import json
import logging
import secrets
from dataclasses import dataclass
from typing import Optional

from services.db import from_row
from services.identity.store import connect

logger = logging.getLogger(__name__)

DIRECTIVE_ID_PREFIX = "dir_"
WILDCARD = "*"

# Action vocabulary (kept narrow on purpose). Extend as use cases come up.
ACTION_REPLY = "reply"            # default — proceed with normal LLM flow
ACTION_IGNORE = "ignore"          # hard: drop silently, no LLM call
ACTION_PRIORITIZE = "prioritize"  # soft: hint to composer
ACTION_AUTO_REPLY = "auto_reply"  # canned reply (payload: {"text": ...})

KNOWN_ACTIONS = {ACTION_IGNORE, ACTION_PRIORITIZE, ACTION_AUTO_REPLY}


@dataclass
class Directive:
    directive_id: str
    issued_by: str
    action: str
    target_person_id: Optional[str]
    scope_platform: str
    scope_workspace: str
    scope_channel: str
    payload_json: Optional[str]
    expires_at: Optional[str]
    source_text: Optional[str]
    created_at: str
    revoked_at: Optional[str]


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _new_directive_id() -> str:
    return DIRECTIVE_ID_PREFIX + secrets.token_hex(6)


def create(
    *,
    issued_by: str,
    action: str,
    target_person_id: Optional[str] = None,
    scope_platform: str = WILDCARD,
    scope_workspace: str = WILDCARD,
    scope_channel: str = WILDCARD,
    payload: Optional[dict] = None,
    expires_at: Optional[str] = None,
    source_text: Optional[str] = None,
) -> str:
    """Insert a directive. Returns directive_id.

    `action` must be one of KNOWN_ACTIONS. `expires_at` is an ISO8601 string
    (use UTC). `payload` is serialized to payload_json.
    """
    if action not in KNOWN_ACTIONS:
        raise ValueError(f"unknown action {action!r}; expected one of {KNOWN_ACTIONS}")
    if not issued_by:
        raise ValueError("issued_by is required")

    directive_id = _new_directive_id()
    payload_json = json.dumps(payload) if payload else None
    now = _now_iso()

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO directives (
                directive_id, issued_by, action, target_person_id,
                scope_platform, scope_workspace, scope_channel,
                payload_json, expires_at, source_text, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                directive_id, issued_by, action, target_person_id,
                scope_platform, scope_workspace, scope_channel,
                payload_json, expires_at, source_text, now,
            ),
        )
    logger.info(
        "[directives] created %s action=%s target=%s scope=(%s/%s/%s)%s",
        directive_id, action, target_person_id,
        scope_platform, scope_workspace, scope_channel,
        f" expires={expires_at}" if expires_at else "",
    )
    return directive_id


def revoke(directive_id: str) -> bool:
    """Mark a directive revoked. Idempotent — returns False if already revoked."""
    with connect() as conn:
        cur = conn.execute(
            "UPDATE directives SET revoked_at = ? WHERE directive_id = ? AND revoked_at IS NULL",
            (_now_iso(), directive_id),
        )
        revoked = cur.rowcount > 0
    if revoked:
        logger.info("[directives] revoked %s", directive_id)
    return revoked


def get(directive_id: str) -> Optional[Directive]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM directives WHERE directive_id = ?", (directive_id,),
        ).fetchone()
    return from_row(Directive, row) if row else None


def list_active_for_person(person_id: str) -> list[Directive]:
    """Active directives that target this person OR are scope-only (target IS NULL).

    Ordering is created_at DESC so callers that don't need full resolver
    semantics (e.g. UI listings) get newest-first.
    """
    now = _now_iso()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM directives
             WHERE revoked_at IS NULL
               AND (expires_at IS NULL OR expires_at > ?)
               AND (target_person_id = ? OR target_person_id IS NULL)
             ORDER BY created_at DESC
            """,
            (now, person_id),
        ).fetchall()
    return [from_row(Directive, r) for r in rows]


def list_active() -> list[Directive]:
    """Every non-revoked, non-expired directive (UI listing / debugging)."""
    now = _now_iso()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM directives
             WHERE revoked_at IS NULL
               AND (expires_at IS NULL OR expires_at > ?)
             ORDER BY created_at DESC
            """,
            (now,),
        ).fetchall()
    return [from_row(Directive, r) for r in rows]


def expire_due() -> int:
    """Move expired directives to revoked state. Returns the count moved.

    Intended to be called from a daily scheduler job. Idempotent — running
    twice in a row will only fire once on each row.
    """
    now = _now_iso()
    with connect() as conn:
        cur = conn.execute(
            """
            UPDATE directives
               SET revoked_at = expires_at
             WHERE revoked_at IS NULL
               AND expires_at IS NOT NULL
               AND expires_at <= ?
            """,
            (now,),
        )
        count = cur.rowcount
    if count:
        logger.info("[directives] expired %d directive(s)", count)
    return count
