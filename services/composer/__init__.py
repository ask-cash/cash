"""Composer layer for Cash.

The composer turns a resolved person + an inbound event into the prompt
context and the platform-appropriate reply. It is the convergence point the
design doc (§11) calls for: instead of each handler hand-rolling its own style
string and history lookup, they share:

  * ``services.composer.base`` — the per-person prompt context (summary +
    recent history + preferences + active soft hints) and a thin Anthropic
    completion helper. Platform-agnostic.

  * ``services.composer.discord`` / ``slack`` / ``teams`` / ``telegram`` — one
    module per surface, each owning that platform's STYLE block and char
    budget. Adding a platform = adding one of these.

``build_person_context`` is the missing §6 step-6 primitive: it reads the
per-person rolling summary (or falls back to the last N messages) so prompt
size stays bounded as Cash talks to more people.
"""

from services.composer.base import (  # noqa: F401
    PersonContext,
    build_person_context,
    complete,
    render_context_block,
)

__all__ = [
    "PersonContext",
    "build_person_context",
    "complete",
    "render_context_block",
]
