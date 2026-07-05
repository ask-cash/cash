"""
base.py — Platform-agnostic event model and the shared inbound pipeline.

This is the spine of the multi-platform architecture. Three pieces:

  * ``IncomingEvent`` — the normalized inbound message. Every adapter produces
    one of these; the brain, the directive resolver, and the composer consume
    only this. They never see a discord.Message or a Slack event dict.

  * ``OutgoingMessage`` — the normalized reply an adapter knows how to send.

  * ``process_incoming(event)`` — the hot path from the design doc (§6):

        1. resolve identity  -> person_id (auto-create on first sight)
        2. log the incoming message (per-person, queryable)
        3. resolve directives -> EffectiveAction
        4. map to a Decision the adapter acts on (ignore / auto_reply / reply / ...)

    It is best-effort and never raises: identity/DB hiccups degrade to a plain
    "reply" Decision so a transient failure can never silently drop a user's
    message or, worse, fail-open past an ``ignore`` rule (a DB failure yields
    ``reply``, which an adapter may still gate — see Decision.should_reply).

The directive precedence and short-circuit semantics live in
``services.directives.resolve`` (a pure function). This module only does the
I/O around it; the security-critical decision stays pure and unit-tested.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from services.directives import resolve as directives_resolve
from services.directives import store as directives_store

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Normalized event / message types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IncomingEvent:
    """A platform-agnostic inbound message.

    ``platform`` + ``platform_user_id`` + ``workspace_id`` is the identity key.
    For platforms with globally-unique user ids (Discord, Telegram), the
    identity layer normalizes ``workspace_id`` to '' so the same human in two
    servers maps to one person — adapters still pass the real workspace through
    for logging and directive scoping.
    """

    platform: str
    platform_user_id: str
    text: str = ""
    workspace_id: Optional[str] = None      # guild / team / Slack workspace
    workspace_name: Optional[str] = None
    channel_id: Optional[str] = None
    channel_name: Optional[str] = None
    display_name: Optional[str] = None
    handle: Optional[str] = None
    message_id: Optional[str] = None
    in_reply_to: Optional[str] = None
    is_owner: bool = False                  # sent by Suhail (authenticated)
    is_direct: bool = False                 # DM / 1:1 channel
    mentions_cash: bool = False
    mentions_owner: bool = False
    raw: Any = None                         # original platform object (adapter-only)
    metadata: dict = field(default_factory=dict)

    def as_directive_event(self, person_id: Optional[str]) -> directives_resolve.Event:
        """Project to the minimal shape the pure resolver needs."""
        return directives_resolve.Event(
            platform=self.platform,
            workspace_id=self.workspace_id,
            channel_id=self.channel_id,
            person_id=person_id,
        )


@dataclass
class OutgoingMessage:
    """A reply an adapter knows how to deliver. ``reply_to`` is the platform
    message id to thread/reply against, when the platform supports it."""

    text: str
    reply_to: Optional[str] = None
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Decision — the output of the inbound pipeline
# ---------------------------------------------------------------------------

# Pipeline-level actions. A superset of directive actions plus the default.
ACT_REPLY = "reply"            # proceed to the composer / LLM
ACT_IGNORE = "ignore"          # hard stop, log as silenced, no LLM
ACT_AUTO_REPLY = "auto_reply"  # send canned text verbatim, no LLM
ACT_PRIORITIZE = "prioritize"  # reply, but flag as high priority to composer


@dataclass
class Decision:
    """What the adapter should do with an event, after rules are applied."""

    action: str
    person_id: Optional[str] = None
    canned_text: Optional[str] = None        # for auto_reply
    soft_hints: list[str] = field(default_factory=list)  # composer guidance
    effective: Optional[directives_resolve.EffectiveAction] = None

    @property
    def should_reply(self) -> bool:
        """True when the adapter should run the composer / LLM path."""
        return self.action in (ACT_REPLY, ACT_PRIORITIZE)

    @property
    def is_silenced(self) -> bool:
        return self.action == ACT_IGNORE

    @property
    def directive_id(self) -> Optional[str]:
        return self.effective.chosen_directive_id if self.effective else None


def decision_from_action(
    action: directives_resolve.EffectiveAction,
    person_id: Optional[str],
) -> Decision:
    """Pure: map a resolver EffectiveAction to a pipeline Decision.

    No I/O — table-driven unit-testable. Keeps the side-effecting pipeline thin
    and the mapping logic in one inspectable place.

    - ``ignore``      -> hard stop
    - ``auto_reply``  -> canned text if present, else fall back to a normal
                         reply (a malformed directive must never wedge a user)
    - ``prioritize``  -> reply, with a soft hint for the composer
    - anything else   -> reply
    """
    act = action.action
    if act == directives_store.ACTION_IGNORE:
        return Decision(action=ACT_IGNORE, person_id=person_id, effective=action)

    if act == directives_store.ACTION_AUTO_REPLY:
        text = (action.payload.get("text") or "").strip()
        if text:
            return Decision(
                action=ACT_AUTO_REPLY,
                person_id=person_id,
                canned_text=text,
                effective=action,
            )
        logger.warning(
            "[pipeline] auto_reply directive %s missing payload.text — replying normally",
            action.chosen_directive_id,
        )
        return Decision(action=ACT_REPLY, person_id=person_id, effective=action)

    if act == directives_store.ACTION_PRIORITIZE:
        return Decision(
            action=ACT_PRIORITIZE,
            person_id=person_id,
            soft_hints=["This person is high priority — answer promptly and attentively."],
            effective=action,
        )

    return Decision(action=ACT_REPLY, person_id=person_id, effective=action)


# ---------------------------------------------------------------------------
# The shared inbound pipeline
# ---------------------------------------------------------------------------

def resolve_directive(event: IncomingEvent, person_id: Optional[str]) -> directives_resolve.EffectiveAction:
    """Look up active directives for ``person_id`` and resolve against ``event``.

    Best-effort: any failure degrades to the default 'reply' action so a DB
    blip never changes who Cash talks to. Synchronous; wrap in
    ``asyncio.to_thread`` from async adapters.
    """
    if not person_id:
        return directives_resolve.EffectiveAction(action=directives_store.ACTION_REPLY)
    try:
        directives = directives_store.list_active_for_person(person_id)
    except Exception:
        logger.exception(
            "[pipeline] list_active_for_person failed for %s — defaulting to reply",
            person_id,
        )
        return directives_resolve.EffectiveAction(action=directives_store.ACTION_REPLY)
    return directives_resolve.effective_action(event.as_directive_event(person_id), directives)


def process_incoming(
    event: IncomingEvent,
    *,
    log: bool = True,
) -> Decision:
    """Run the §6 hot path for one inbound event and return a Decision.

    Steps: resolve identity -> log incoming -> resolve directives -> map to a
    Decision. Synchronous and best-effort; wrap in ``asyncio.to_thread`` from
    async callers. Identity and logging failures are swallowed (they must not
    drop the message); the directive lookup degrades to 'reply' on error.
    """
    # Imported lazily so the pure decision_from_action / resolve helpers stay
    # importable in tests without pulling in the identity/state-store stack.
    from services.identity import people as identity_people

    person_id: Optional[str] = None
    try:
        person_id = identity_people.resolve(
            platform=event.platform,
            platform_user_id=event.platform_user_id,
            workspace_id=event.workspace_id,
            display_name=event.display_name,
            handle=event.handle,
        )
    except Exception:
        logger.exception(
            "[pipeline] identity.resolve failed for %s/%s — continuing without person_id",
            event.platform, event.platform_user_id,
        )

    if log:
        _log_incoming(event, person_id)

    action = resolve_directive(event, person_id)
    decision = decision_from_action(action, person_id)

    if decision.is_silenced:
        logger.info(
            "[pipeline] silenced %s msg=%s person=%s per directive=%s",
            event.platform, event.message_id, person_id, decision.directive_id,
        )
        if log:
            _log_silenced(event, person_id, decision.directive_id)
    return decision


def _log_incoming(event: IncomingEvent, person_id: Optional[str]) -> None:
    try:
        from services.memory import log_message
        log_message(
            "user", event.text or "",
            metadata={
                "surface": event.platform,
                "person_id": person_id,
                "workspace_id": event.workspace_id,
                "channel_id": event.channel_id,
                "channel_name": event.channel_name,
                "author_id": event.platform_user_id,
                "author_name": event.display_name,
                "message_id": event.message_id,
            },
        )
    except Exception:
        logger.exception("[pipeline] failed to log incoming event")


def _log_silenced(event: IncomingEvent, person_id: Optional[str], directive_id: Optional[str]) -> None:
    try:
        from services.memory import log_message
        log_message(
            "assistant", "[silenced per ignore directive]",
            metadata={
                "surface": event.platform,
                "person_id": person_id,
                "channel_id": event.channel_id,
                "in_reply_to": event.message_id,
                "outcome": "silent-by-directive",
                "directive_id": directive_id,
            },
        )
    except Exception:
        logger.exception("[pipeline] failed to log silenced event")


# ---------------------------------------------------------------------------
# The adapter contract
# ---------------------------------------------------------------------------

class PlatformAdapter(ABC):
    """Base class every platform adapter implements.

    Concrete adapters set ``name`` (matches the ``platform`` column),
    ``max_chars`` (the platform's per-message limit) and ``workspace_is_global``
    (True for Discord/Telegram where a user id is unique across workspaces).
    """

    name: str = "base"
    max_chars: int = 2000
    workspace_is_global: bool = False

    @abstractmethod
    def normalize(self, raw_event: Any) -> Optional[IncomingEvent]:
        """Map a raw platform payload to an IncomingEvent (or None to skip)."""

    @abstractmethod
    async def send(self, event: IncomingEvent, message: OutgoingMessage) -> Optional[str]:
        """Deliver ``message`` in response to ``event``. Returns the sent
        message id when the platform exposes one, else None."""

    def clamp(self, text: str) -> str:
        """Truncate to the platform's char limit, keeping an ellipsis."""
        if text is None:
            return ""
        if len(text) <= self.max_chars:
            return text
        return text[: self.max_chars - 3].rstrip() + "..."

    def process(self, event: IncomingEvent) -> Decision:
        """Convenience: run the shared pipeline for an already-normalized event."""
        return process_incoming(event)
