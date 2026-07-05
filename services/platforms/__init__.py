"""Platform adapter layer for Cash.

An *adapter* is the only part of Cash that knows what a Discord message, a
Slack event, a Teams activity, or a Telegram update actually looks like. Each
adapter does three things (see services.platforms.base.PlatformAdapter):

  1. ``normalize(raw_event) -> IncomingEvent`` — map a raw platform payload to
     the platform-agnostic ``IncomingEvent`` the brain understands.
  2. ``send(event, OutgoingMessage)`` — deliver a reply through the platform's
     native API, owning its quirks (mention syntax, threading, char limits).
  3. Carry platform-specific identity rules (global vs. workspace-scoped user
     ids) via the ``workspace_is_global`` flag.

Everything downstream — the directive resolver, the composer, the per-person
memory — consumes only ``IncomingEvent`` and never imports a platform SDK.
That is what makes "add Slack later" a single-file change.

The shared hot path lives in ``services.platforms.base.process_incoming``:
resolve identity -> log -> resolve directives -> return a ``Decision``. Every
adapter funnels through it so the security-critical rules (ignore, auto_reply)
are enforced identically on every platform, in code, before any LLM runs.
"""

from services.platforms.base import (  # noqa: F401
    Decision,
    IncomingEvent,
    OutgoingMessage,
    PlatformAdapter,
    decision_from_action,
    process_incoming,
)

__all__ = [
    "Decision",
    "IncomingEvent",
    "OutgoingMessage",
    "PlatformAdapter",
    "decision_from_action",
    "process_incoming",
]
