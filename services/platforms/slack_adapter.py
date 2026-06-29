"""
slack_adapter.py — Slack <-> IncomingEvent normalization and sending.

Normalizes a Slack Events API payload (a ``message`` or ``app_mention`` event
object) into an IncomingEvent, and sends replies via a caller-supplied
``send_fn`` (typically ``WebClient.chat_postMessage`` from slack_sdk). Keeping
the transport behind a callback means the normalization — the part with all
the platform quirks — is fully unit-testable without a live Slack connection
or the slack_sdk dependency.

Slack user ids are WORKSPACE-SCOPED: the same ``U03ABC`` in two unrelated
workspaces is two different humans. So ``workspace_is_global = False`` and the
identity layer preserves ``workspace_id`` (the Slack team id) in the identity
key.

Wiring status: the normalization + send-payload shaping below is complete and
tested. Connecting it to a live Slack app (Bolt/Socket Mode or an Events API
webhook on the gateway, plus a bot token) is the remaining follow-up — see
docs/architecture/cash-platform-adapters.md.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, Optional

from services.composer import slack as slack_style
from services.platforms.base import IncomingEvent, OutgoingMessage, PlatformAdapter

logger = logging.getLogger(__name__)

# <@U123ABC> mention syntax used in Slack message text.
_MENTION_RE = re.compile(r"<@([A-Z0-9]+)>")
# Slack message subtypes that are not real user messages (joins, edits, bots).
_IGNORED_SUBTYPES = {
    "bot_message", "message_changed", "message_deleted",
    "channel_join", "channel_leave", "channel_topic",
}


class SlackAdapter(PlatformAdapter):
    name = "slack"
    max_chars = slack_style.MAX_CHARS
    workspace_is_global = False

    def __init__(
        self,
        *,
        cash_bot_user_id: str,
        owner_user_id: Optional[str] = None,
        send_fn: Optional[Callable[..., Any]] = None,
    ):
        self.cash_bot_user_id = cash_bot_user_id
        self.owner_user_id = owner_user_id
        self._send_fn = send_fn

    def normalize(self, raw_event: Any) -> Optional[IncomingEvent]:
        """Map a Slack event object to an IncomingEvent.

        Accepts either the full Events API envelope ({"event": {...}, "team_id":
        ...}) or the inner event object directly. Returns None for bot messages,
        non-message events, and edit/join subtypes.
        """
        envelope = raw_event if isinstance(raw_event, dict) else {}
        event = envelope.get("event", envelope)
        team_id = envelope.get("team_id") or event.get("team")

        ev_type = event.get("type")
        if ev_type not in ("message", "app_mention"):
            return None
        if event.get("subtype") in _IGNORED_SUBTYPES:
            return None
        # Bot/self messages have a bot_id or no human user.
        if event.get("bot_id") or not event.get("user"):
            return None

        user_id = event["user"]
        text = event.get("text") or ""
        mentioned = set(_MENTION_RE.findall(text))

        return IncomingEvent(
            platform=self.name,
            platform_user_id=str(user_id),
            text=_strip_mentions(text),
            workspace_id=str(team_id) if team_id else None,
            channel_id=event.get("channel"),
            channel_name=event.get("channel_name"),
            handle=event.get("user_name"),
            message_id=event.get("ts"),
            in_reply_to=event.get("thread_ts"),
            is_owner=(self.owner_user_id is not None and user_id == self.owner_user_id),
            is_direct=(event.get("channel_type") == "im"),
            mentions_cash=(ev_type == "app_mention" or self.cash_bot_user_id in mentioned),
            mentions_owner=(self.owner_user_id in mentioned if self.owner_user_id else False),
            raw=event,
            metadata={"team_id": team_id},
        )

    def build_send_payload(self, event: IncomingEvent, message: OutgoingMessage) -> dict:
        """Pure: shape a chat.postMessage payload. Threads under the source ts."""
        payload = {
            "channel": event.channel_id,
            "text": self.clamp(message.text),
        }
        thread_ts = message.reply_to or event.in_reply_to or event.message_id
        if thread_ts:
            payload["thread_ts"] = thread_ts
        return payload

    async def send(self, event: IncomingEvent, message: OutgoingMessage) -> Optional[str]:
        if self._send_fn is None:
            raise RuntimeError(
                "SlackAdapter has no send_fn configured — pass a chat.postMessage "
                "callable (e.g. slack_sdk WebClient.chat_postMessage) to enable sending."
            )
        payload = self.build_send_payload(event, message)
        result = self._send_fn(**payload)
        # slack_sdk returns a SlackResponse / dict with a "ts".
        try:
            return (result or {}).get("ts")
        except AttributeError:
            return None


def _strip_mentions(text: str) -> str:
    """Remove <@U...> mention tokens so the brain sees clean prose."""
    return _MENTION_RE.sub("", text or "").strip()
