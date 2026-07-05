"""
resolve.py — Pure-function conflict resolver.

Given an inbound `Event` and a list of `Directive` rows, return one
`EffectiveAction`. No DB access, no I/O, no side effects — the function is
deterministic on its inputs. This is the regression-test target.

Precedence rules (highest priority first)
-----------------------------------------
1. Filter to ACTIVE directives (revoked_at IS NULL AND expires_at not past)
   that match the event's scope (platform/workspace/channel — wildcards
   match anything) AND target this person (or have target_person_id NULL,
   meaning "scope-only — applies to everyone in this scope").

2. Among remaining matches, score specificity:
       target-specific      +8
       channel scope set    +4
       workspace scope set  +2
       platform scope set   +1
   Higher score wins. This means a channel-scoped auto_reply for a specific
   person beats a global ignore for the same person — the explicit narrow
   rule is the more recent intent.

3. At EQUAL specificity, a hard ``ignore`` wins over softer actions. This is
   the design doc's "hard actions short-circuit" rule (§3.1.3): if Suhail has
   both an ignore and a prioritize on the same person at the same scope, the
   safe choice (stay silent) wins. Note this only applies at equal specificity
   — a narrower auto_reply (e.g. channel-scoped) still beats a broader ignore,
   because the explicit narrow rule is the more deliberate intent (rule 1).

4. Tiebreak by created_at — newer wins. So when Suhail issues a second
   directive at the same scope and action class, it supersedes the first
   without needing to revoke the old one explicitly.

4. The winning directive's action is the EffectiveAction. If no directive
   matches, the action is "reply" (default — Cash behaves normally).

Notes for callers
-----------------
- Hard actions (today: ignore) are intended to short-circuit the LLM. Check
  EffectiveAction.action == "ignore" before composing or sending.
- Soft actions (prioritize, auto_reply) flow through to the composer as
  guidance / canned text. The payload dict carries any per-action params.
- If you find yourself wanting to "combine" multiple directives (e.g. both
  an auto_reply text AND a prioritize hint), don't — issue one directive
  per intent and let the resolver pick. Combining means lying about
  precedence.
"""

import datetime as dt
import json
from dataclasses import dataclass, field
from typing import Optional

from services.directives.store import (
    ACTION_IGNORE,
    ACTION_REPLY,
    WILDCARD,
    Directive,
)


@dataclass(frozen=True)
class Event:
    """Normalized inbound message — what the resolver needs to decide."""
    platform: str
    workspace_id: Optional[str] = None
    channel_id: Optional[str] = None
    person_id: Optional[str] = None


@dataclass
class EffectiveAction:
    action: str                           # "reply" (default), "ignore", "prioritize", "auto_reply"
    payload: dict = field(default_factory=dict)
    chosen_directive_id: Optional[str] = None
    matching_directive_ids: list[str] = field(default_factory=list)

    @property
    def is_default(self) -> bool:
        return self.action == ACTION_REPLY and self.chosen_directive_id is None


def _is_active(d: Directive, now_iso: str) -> bool:
    if d.revoked_at:
        return False
    if d.expires_at and d.expires_at <= now_iso:
        return False
    return True


def _matches_scope(d: Directive, event: Event) -> bool:
    if d.scope_platform != WILDCARD and d.scope_platform != event.platform:
        return False
    if d.scope_workspace != WILDCARD and d.scope_workspace != (event.workspace_id or ""):
        return False
    if d.scope_channel != WILDCARD and d.scope_channel != (event.channel_id or ""):
        return False
    return True


def _matches_target(d: Directive, event: Event) -> bool:
    if d.target_person_id is None:
        return True  # scope-only directive — applies to everyone in scope
    return d.target_person_id == event.person_id


def _specificity(d: Directive) -> int:
    score = 0
    if d.target_person_id is not None:
        score += 8
    if d.scope_channel != WILDCARD:
        score += 4
    if d.scope_workspace != WILDCARD:
        score += 2
    if d.scope_platform != WILDCARD:
        score += 1
    return score


def _hard_rank(d: Directive) -> int:
    """1 for hard short-circuit actions (ignore), else 0. Used only to break
    ties at EQUAL specificity so the safe action wins (design doc §3.1.3)."""
    return 1 if d.action == ACTION_IGNORE else 0


def effective_action(
    event: Event,
    directives: list[Directive],
    *,
    now: Optional[dt.datetime] = None,
) -> EffectiveAction:
    """Pure: pick the winning directive for this event. Default → 'reply'."""
    if now is None:
        now = dt.datetime.now(dt.timezone.utc)
    now_iso = now.isoformat()

    matching = [
        d for d in directives
        if _is_active(d, now_iso)
        and _matches_scope(d, event)
        and _matches_target(d, event)
    ]
    if not matching:
        return EffectiveAction(action=ACTION_REPLY)

    matching.sort(
        key=lambda d: (_specificity(d), _hard_rank(d), d.created_at),
        reverse=True,
    )
    winner = matching[0]
    payload = json.loads(winner.payload_json) if winner.payload_json else {}

    return EffectiveAction(
        action=winner.action,
        payload=payload,
        chosen_directive_id=winner.directive_id,
        matching_directive_ids=[d.directive_id for d in matching],
    )
