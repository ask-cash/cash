"""
telegram_adapter.py — Telegram <-> IncomingEvent normalization and sending.

Wraps a python-telegram-bot ``Update`` into an IncomingEvent. Telegram is
Suhail's private owner channel; ``is_owner`` is set when the sender matches the
configured owner id. Telegram user ids are global, so
``workspace_is_global = True`` and ``workspace_id`` collapses to '' in the
identity layer.

The main Telegram flow still runs through ``services.ai_brain`` (full action
surface). This adapter exists so non-brain Telegram paths — and a future
``compose_for_owner`` — share the same normalization and the same inbound
pipeline as every other platform.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from services.composer import telegram as telegram_style
from services.platforms.base import IncomingEvent, OutgoingMessage, PlatformAdapter

logger = logging.getLogger(__name__)


class TelegramAdapter(PlatformAdapter):
    name = "telegram"
    max_chars = telegram_style.MAX_CHARS
    workspace_is_global = True

    def __init__(self, *, owner_id: Optional[int] = None):
        self.owner_id = owner_id

    def normalize(self, raw_event: Any) -> Optional[IncomingEvent]:
        """Map a telegram.Update to an IncomingEvent. None if there's no text."""
        update = raw_event
        msg = getattr(update, "message", None)
        user = getattr(update, "effective_user", None)
        chat = getattr(update, "effective_chat", None)
        if msg is None or user is None:
            return None
        text = getattr(msg, "text", None)
        if not text:
            return None

        return IncomingEvent(
            platform=self.name,
            platform_user_id=str(user.id),
            text=text,
            channel_id=str(chat.id) if chat else None,
            channel_name=getattr(chat, "title", None),
            display_name=getattr(user, "full_name", None),
            handle=getattr(user, "username", None),
            message_id=str(msg.message_id) if getattr(msg, "message_id", None) else None,
            is_owner=(self.owner_id is not None and user.id == self.owner_id),
            is_direct=(getattr(chat, "type", "private") == "private"),
            raw=update,
            metadata={},
        )

    async def send(self, event: IncomingEvent, message: OutgoingMessage) -> Optional[str]:
        """Reply via the originating Update's message object."""
        update = event.raw
        msg = getattr(update, "message", None)
        if msg is None:
            logger.warning("[telegram_adapter] no message to reply to")
            return None
        sent = await msg.reply_text(self.clamp(message.text))
        return str(getattr(sent, "message_id", "")) or None
