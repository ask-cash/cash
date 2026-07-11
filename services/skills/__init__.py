"""
skills — Cash's declarative skill-pack system (Feature 6).

Importing this package registers every pack under ``packs/`` into the registry,
so ``ai_brain`` can project the action contract from the active packs each turn.
The public surface mirrors ``registry``.
"""

from services.skills.registry import (  # noqa: F401
    Skill,
    register,
    all_skills,
    active_skills,
    get,
    owner_of,
    is_enabled,
    is_action_enabled,
    is_flag_enabled,
    set_flag_enabled,
    build_action_contract,
)

# Import each pack for its registration side effect. Order here doesn't matter —
# projection order comes from each Skill's ``order`` field.
from services.skills.packs import (  # noqa: F401,E402
    core,
    tasks,
    calendar,
    trading,
    briefing,
    reminders,
    profile,
    cross_platform,
    memory,
    calendars_status,
    email,
    files,
)
