"""Behavior layer for Cash.

A `Directive` is a structured rule issued by Suhail that constrains how Cash
treats a person, scope, or both. The resolver is a pure function: given an
event and the active directive set, it returns the EffectiveAction. Hard
rules (ignore) bypass the LLM entirely; soft rules (prioritize, auto_reply)
flow through as guidance the composer honors.

Modules
-------
- store     CRUD on the directives table.
- resolve   Pure function (event, directives) -> EffectiveAction.
            Lock its behavior with regression tests before relying on it
            in production code.
"""

from services.directives.parser import (  # noqa: F401
    DEFAULT_CONFIDENCE_THRESHOLD,
    DirectiveProposal,
    looks_like_instruction,
    parse,
)
from services.directives.resolve import (  # noqa: F401
    EffectiveAction,
    Event,
    effective_action,
)
from services.directives.store import (  # noqa: F401
    Directive,
    create,
    expire_due,
    get,
    list_active,
    list_active_for_person,
    revoke,
)
