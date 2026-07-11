"""
registry.py — Cash's skill-pack registry (Feature 6).

Cash's adaptation of Vellum's skill catalog + runtime tool projection. A **skill
pack** bundles, for one capability cluster:

  * an ``id`` and human title,
  * the action-contract *prompt fragment* it contributes (the "Available actions"
    bullets, plus any rules specific to that cluster),
  * the set of ``actions`` (action names) it owns,
  * a ``flag`` so the whole pack can be switched off, and
  * an ``order`` so the projected contract reads in a stable sequence.

Per turn, ``ai_brain`` asks the registry to **project** the action contract from
the *active* packs only (``build_action_contract``). Disabling a pack's flag
removes its actions from the prompt AND lets the handler refuse them
(``is_action_enabled``) — so a disabled capability disappears from every surface.

Execution itself still lives in the platform handlers (``bot/handlers``); this
registry owns the *declaration* and *projection*, which is what let us delete the
hardcoded action list from ``ai_brain``. The flag store is tenant-scoped state,
degrading to "enabled" when there's no tenant context (mirrors services.persona).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from services import state_store

logger = logging.getLogger(__name__)

_FLAG_NS = "skill_flags"
_FLAG_KEY = "disabled"          # list[str] of disabled flag names


@dataclass(frozen=True)
class Skill:
    """One declarative capability bundle."""

    id: str
    title: str
    order: int
    actions: tuple[str, ...]
    prompt: str
    flag: str
    always_on: bool = False     # core packs (e.g. chat) can never be disabled


_REGISTRY: dict[str, Skill] = {}


def register(skill: Skill) -> Skill:
    """Add a pack to the registry. Idempotent by id (re-register overwrites)."""
    _REGISTRY[skill.id] = skill
    return skill


def all_skills() -> list[Skill]:
    """Every registered pack, in projection order."""
    return sorted(_REGISTRY.values(), key=lambda s: (s.order, s.id))


def get(skill_id: str) -> Optional[Skill]:
    return _REGISTRY.get(skill_id)


# ---------------------------------------------------------------------------
# Flags — a pack is enabled unless its flag is explicitly disabled
# ---------------------------------------------------------------------------

def _disabled_flags() -> set[str]:
    try:
        raw = state_store.read_json(_FLAG_NS, _FLAG_KEY, default=[]) or []
        return set(raw)
    except Exception:
        # No tenant context / store hiccup: fail *open* (everything enabled) so a
        # storage blip can never silently strip Cash of her capabilities.
        return set()


def is_flag_enabled(flag: str) -> bool:
    return flag not in _disabled_flags()


def set_flag_enabled(flag: str, enabled: bool) -> None:
    disabled = _disabled_flags()
    if enabled:
        disabled.discard(flag)
    else:
        disabled.add(flag)
    state_store.write_json(_FLAG_NS, _FLAG_KEY, sorted(disabled))


def is_enabled(skill: Skill) -> bool:
    return skill.always_on or is_flag_enabled(skill.flag)


def active_skills() -> list[Skill]:
    """Packs that should contribute to this turn."""
    return [s for s in all_skills() if is_enabled(s)]


# ---------------------------------------------------------------------------
# Action ownership + gating
# ---------------------------------------------------------------------------

def owner_of(action: str) -> Optional[Skill]:
    """The pack that owns ``action``, or None if no pack claims it."""
    for skill in _REGISTRY.values():
        if action in skill.actions:
            return skill
    return None


def is_action_enabled(action: str) -> bool:
    """True if ``action`` may run.

    Unowned actions (legacy / not yet migrated) are always allowed — the gate
    only constrains actions a pack explicitly claims. Owned actions follow their
    pack's flag.
    """
    skill = owner_of(action)
    return True if skill is None else is_enabled(skill)


# ---------------------------------------------------------------------------
# Projection — assemble the action contract from active packs
# ---------------------------------------------------------------------------

def build_action_contract() -> str:
    """The "Available actions" body, projected from the active packs in order."""
    return "\n".join(s.prompt.strip() for s in active_skills())
