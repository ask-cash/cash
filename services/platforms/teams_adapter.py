"""
teams_adapter.py — Microsoft Teams <-> IncomingEvent normalization and sending.

Normalizes a Bot Framework ``Activity`` (the JSON Teams posts to a messaging
endpoint) into an IncomingEvent, and sends replies via a caller-supplied
``send_fn``. As with Slack, keeping transport behind a callback makes the
normalization unit-testable without botbuilder or a live Teams channel.

Identity: Teams users are identified by their AAD object id, which is
workspace- (tenant-) scoped in the same way Slack ids are. So
``workspace_is_global = False`` and the identity layer keeps ``workspace_id``
(the Teams/tenant id) in the key.

Wiring status: normalization + reply-Activity shaping below is complete and
tested. Standing up the messaging endpoint (Bot Framework adapter on the
gateway, app id/password, the connector to POST the reply Activity) is the
remaining follow-up — see docs/architecture/cash-platform-adapters.md.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, Optional

from services.composer import teams as teams_style
from services.platforms.base import IncomingEvent, OutgoingMessage, PlatformAdapter

logger = logging.getLogger(__name__)

# Teams wraps mentions in <at>Display Name</at> tags in the activity text.
_AT_TAG_RE = re.compile(r"<at>(.*?)</at>", re.IGNORECASE | re.DOTALL)


class TeamsAdapter(PlatformAdapter):
    name = "teams"
    max_chars = teams_style.MAX_CHARS
    workspace_is_global = False

    def __init__(
        self,
        *,
        cash_bot_id: str,
        owner_aad_id: Optional[str] = None,
        send_fn: Optional[Callable[..., Any]] = None,
    ):
        self.cash_bot_id = cash_bot_id
        self.owner_aad_id = owner_aad_id
        self._send_fn = send_fn

    def normalize(self, raw_event: Any) -> Optional[IncomingEvent]:
        """Map a Bot Framework Activity dict to an IncomingEvent.

        Returns None for non-message activities (typing indicators, reactions,
        conversation updates) and for the bot's own messages.
        """
        activity = raw_event if isinstance(raw_event, dict) else {}
        if activity.get("type") != "message":
            return None

        from_obj = activity.get("from") or {}
        user_id = from_obj.get("aadObjectId") or from_obj.get("id")
        if not user_id:
            return None
        # Skip the bot's own activities.
        if from_obj.get("id") and from_obj.get("id") == self.cash_bot_id:
            return None

        conversation = activity.get("conversation") or {}
        channel_data = activity.get("channelData") or {}
        tenant_id = (channel_data.get("tenant") or {}).get("id") or activity.get("serviceUrl")

        mention_ids, mentioned_cash, mentioned_owner = self._scan_mentions(activity)

        return IncomingEvent(
            platform=self.name,
            platform_user_id=str(user_id),
            text=_strip_at_tags(activity.get("text") or ""),
            workspace_id=str(tenant_id) if tenant_id else None,
            channel_id=conversation.get("id"),
            channel_name=conversation.get("name"),
            display_name=from_obj.get("name"),
            handle=from_obj.get("name"),
            message_id=activity.get("id"),
            in_reply_to=(activity.get("replyToId")),
            is_owner=(self.owner_aad_id is not None and str(user_id) == self.owner_aad_id),
            is_direct=(conversation.get("conversationType") == "personal"),
            mentions_cash=mentioned_cash,
            mentions_owner=mentioned_owner,
            raw=activity,
            metadata={"tenant_id": tenant_id, "service_url": activity.get("serviceUrl")},
        )

    def _scan_mentions(self, activity: dict) -> tuple[set, bool, bool]:
        ids = set()
        cash = False
        owner = False
        for entity in activity.get("entities") or []:
            if entity.get("type") != "mention":
                continue
            mentioned = (entity.get("mentioned") or {}).get("id")
            if not mentioned:
                continue
            ids.add(mentioned)
            if mentioned == self.cash_bot_id:
                cash = True
            if self.owner_aad_id and mentioned == self.owner_aad_id:
                owner = True
        return ids, cash, owner

    def build_reply_activity(self, event: IncomingEvent, message: OutgoingMessage) -> dict:
        """Pure: shape a Bot Framework reply Activity for the source conversation."""
        src = event.raw or {}
        conversation = src.get("conversation") or {}
        return {
            "type": "message",
            "text": self.clamp(message.text),
            "conversation": conversation,
            "replyToId": event.message_id,
            "serviceUrl": (event.metadata or {}).get("service_url"),
            "from": {"id": self.cash_bot_id},
            "recipient": src.get("from") or {},
        }

    async def send(self, event: IncomingEvent, message: OutgoingMessage) -> Optional[str]:
        if self._send_fn is None:
            raise RuntimeError(
                "TeamsAdapter has no send_fn configured — pass a callable that "
                "POSTs a reply Activity (Bot Framework connector) to enable sending."
            )
        activity = self.build_reply_activity(event, message)
        result = self._send_fn(activity)
        try:
            return (result or {}).get("id")
        except AttributeError:
            return None


def _strip_at_tags(text: str) -> str:
    """Drop <at>...</at> mention tags, leaving clean prose for the brain."""
    return _AT_TAG_RE.sub("", text or "").strip()
