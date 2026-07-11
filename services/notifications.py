"""
notifications.py — the proactive-message decision engine (Feature 5).

"One Cash, one memory, every channel." Producers of *unprompted* messages —
the heartbeat, follow-up sweeps, reminders, briefings, alerts — don't decide
where or whether to speak. They ``emit_signal(...)`` and this module does:

  1. **decide** — pick the channel (routing hint > guardian's preferred surface
     > default), and whether the moment is right to speak at all. A low-urgency
     nudge is *suppressed* while the guardian is mid-conversation with Cash, so
     Cash never talks over an active turn. Time-critical signals (reminders,
     explicit alerts) always go through.
  2. **dispatch** — for connector-backed platforms (Discord/Slack/Teams) it
     drops the message on that platform's Redis outbound topic, which the live
     connector drains and DMs the guardian (see ``services.queue`` +
     ``app.discord_connector``). Telegram is the in-process JobQueue owner, so
     its jobs deliver the returned decision themselves on the event loop.

The decision half (``decide``) is a pure function of a Signal + the activity
clock and is unit-tested in isolation. The I/O half (activity clock, preferred
channel) is tenant-scoped state, mirroring every other service here.

Design refs: cash-cross-platform-presence.md §2 (outbound spine),
cash-system-architecture §6 (send_platform_message).
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from dataclasses import dataclass, field

from services import queue
from services import state_store
from services.tenancy import current_tenant_id
from services.user_profile import now as _now

logger = logging.getLogger(__name__)

NAMESPACE = "notifications"
_ACTIVITY_KEY = "activity"          # {platform: last_inbound_iso, "_last": iso}
_PREF_KEY = "preferred_channel"     # platform string chosen by the guardian

# ---------------------------------------------------------------------------
# Signal kinds + urgency policy
# ---------------------------------------------------------------------------

KIND_HEARTBEAT = "heartbeat"
KIND_FOLLOWUP = "followup"
KIND_REMINDER = "reminder"
KIND_BRIEFING = "briefing"
KIND_ALERT = "alert"

# Kinds that may be held back while the guardian is actively talking to Cash.
# Everything else (reminders the guardian explicitly set, alerts) is
# time-critical and delivered even mid-conversation.
_SUPPRESSIBLE = {KIND_HEARTBEAT, KIND_FOLLOWUP, KIND_BRIEFING}

# Platforms delivered via the Redis outbound topic + live connector. Telegram is
# absent on purpose: its proactive jobs run in-process on the JobQueue and hold
# the bot handle, so they deliver the decision directly.
_QUEUE_BACKED = {"discord", "slack", "teams"}

DEFAULT_CHANNEL = "telegram"

# How long after the guardian's last message we treat the conversation as still
# "active" (seconds). A heartbeat firing inside this window is suppressed.
ACTIVE_WINDOW_SECONDS = 180

# decide() outcomes
DELIVER = "deliver"
SUPPRESS = "suppress"


@dataclass
class Signal:
    """A proactive message a producer wants Cash to send.

    ``routing`` hints: ``channel`` (force a surface), ``to`` (default "owner"),
    ``urgent`` (force delivery even mid-conversation).
    """

    kind: str
    text: str
    routing: dict = field(default_factory=dict)


@dataclass
class Decision:
    """The router's verdict for a Signal."""

    outcome: str                    # DELIVER | SUPPRESS
    channel: str = DEFAULT_CHANNEL
    to: str = "owner"
    reuse: bool = False             # thread into the active chat vs a fresh ping
    reason: str = ""
    dispatched: bool = False        # True once handed to a queue-backed connector

    @property
    def should_deliver(self) -> bool:
        return self.outcome == DELIVER


# ---------------------------------------------------------------------------
# Activity clock — "is the guardian mid-conversation right now?"
# ---------------------------------------------------------------------------

def touch_activity(platform: str) -> None:
    """Record that the guardian just sent Cash a message on ``platform``.

    Called from the inbound handlers. Cheap (one small json write). Used purely
    to suppress proactive pings during an active turn — best-effort, so any
    failure is swallowed rather than blocking the reply path.
    """
    try:
        data = state_store.read_json(NAMESPACE, _ACTIVITY_KEY, default={}) or {}
        stamp = _now().isoformat()
        data[platform] = stamp
        data["_last"] = stamp
        state_store.write_json(NAMESPACE, _ACTIVITY_KEY, data)
    except Exception:
        logger.exception("[notifications] touch_activity failed for %s", platform)


def seconds_since_last_activity(platform: str | None = None) -> float | None:
    """Seconds since the guardian last spoke (on ``platform``, or any channel).

    None if we've never seen inbound activity.
    """
    data = state_store.read_json(NAMESPACE, _ACTIVITY_KEY, default={}) or {}
    stamp = data.get(platform) if platform else data.get("_last")
    if not stamp:
        return None
    try:
        last = dt.datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return None
    ref = _now()
    if last.tzinfo is None and ref.tzinfo is not None:
        ref = ref.replace(tzinfo=None)
    return (ref - last).total_seconds()


def is_conversation_active(platform: str | None = None,
                           window_seconds: int = ACTIVE_WINDOW_SECONDS) -> bool:
    """True if the guardian spoke within the active window on this channel."""
    elapsed = seconds_since_last_activity(platform)
    return elapsed is not None and 0 <= elapsed < window_seconds


# ---------------------------------------------------------------------------
# Preferred proactive channel (guardian setting; surfaced in the dashboard)
# ---------------------------------------------------------------------------

def get_preferred_channel(default: str = DEFAULT_CHANNEL) -> str:
    try:
        return state_store.read_json(NAMESPACE, _PREF_KEY, default=None) or default
    except Exception:
        return default


def set_preferred_channel(platform: str) -> None:
    platform = (platform or "").strip().lower()
    if not platform:
        raise ValueError("platform must be a non-empty string")
    state_store.write_json(NAMESPACE, _PREF_KEY, platform)


# ---------------------------------------------------------------------------
# The decision — pure given (signal, active-flag)
# ---------------------------------------------------------------------------

def decide(signal: Signal, *, active: bool | None = None) -> Decision:
    """Route a Signal: choose channel + whether to speak now.

    Pure when ``active`` is supplied; otherwise it consults the activity clock.
    Policy:
      * channel = routing["channel"] > guardian's preferred channel > default.
      * urgent = routing["urgent"] OR the kind isn't in the suppressible set.
      * if the guardian is mid-conversation on that channel and the signal is
        not urgent -> SUPPRESS (don't talk over an active turn).
      * otherwise DELIVER, threading into the active chat (reuse) if one is open.
    """
    routing = signal.routing or {}
    channel = (routing.get("channel") or get_preferred_channel()).strip().lower()
    to = routing.get("to") or "owner"
    urgent = bool(routing.get("urgent")) or signal.kind not in _SUPPRESSIBLE

    if active is None:
        active = is_conversation_active(channel)

    if active and not urgent:
        return Decision(outcome=SUPPRESS, channel=channel, to=to,
                        reason="active-conversation")

    return Decision(outcome=DELIVER, channel=channel, to=to, reuse=bool(active),
                    reason="urgent" if urgent else "quiet")


# ---------------------------------------------------------------------------
# The producer entry point
# ---------------------------------------------------------------------------

def emit_signal(kind: str, text: str, routing: dict | None = None) -> Decision:
    """Decide + dispatch a proactive message. Returns the Decision.

    For queue-backed channels (Discord/Slack/Teams) this enqueues the outbound
    job here (sync-safe, so it's fine to call from an ``asyncio.to_thread``
    worker) and marks the decision ``dispatched``. For Telegram it only decides;
    the caller (a JobQueue job holding the bot) delivers ``text`` in-process when
    ``decision.channel == "telegram"`` and ``decision.should_deliver``.

    Never raises for a delivery hiccup — a dropped nudge must not crash a job.
    """
    decision = decide(Signal(kind=kind, text=text, routing=routing or {}))
    if not decision.should_deliver:
        return decision
    if decision.channel in _QUEUE_BACKED:
        try:
            _enqueue_outbound(decision, text)
            decision.dispatched = True
        except Exception:
            logger.exception("[notifications] outbound enqueue failed for %s", decision.channel)
    return decision


def _enqueue_outbound(decision: Decision, text: str) -> None:
    tenant_id = current_tenant_id()
    queue.enqueue_outbound(decision.channel, tenant_id, {
        "to": decision.to,
        "text": text,
        "idempotency_key": uuid.uuid4().hex,
    })
