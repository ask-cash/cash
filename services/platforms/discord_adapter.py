"""
discord_adapter.py — Discord <-> IncomingEvent normalization and sending.

Wraps a live ``discord.Message`` into the platform-agnostic IncomingEvent and
sends OutgoingMessages via ``message.reply``. The existing
``bot/handlers/discord_messages.py`` keeps owning the event *dispatch* (the
mention routing, the deferred-proxy queue, reaction/delete cancellation) and
delegates the identity + directive decision to ``base.process_incoming`` via
this adapter — so the security-critical rules run through one shared path.

Discord user ids are global, so ``workspace_is_global = True``: the identity
layer collapses ``workspace_id`` to '' and one human across two guilds maps to
one person.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from services.composer import discord as discord_style
from services.platforms.base import IncomingEvent, OutgoingMessage, PlatformAdapter

logger = logging.getLogger(__name__)


async def deliver(client: Any, user_id: int, text: str, *, max_chars: int = discord_style.MAX_CHARS) -> str:
    """Initiate a DM to a Discord user by id (Cash-initiated, not a reply).

    Used by the connector's outbound consumer. Separate from ``DiscordAdapter.send``
    (which replies to an inbound message) because outbound delivery has no source
    event and must open the DM channel itself. Returns the sent message id.

    Raises on failure (user not found, DMs closed, no mutual guild) so the caller
    can log/report — never silently swallows.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("refusing to deliver empty message")
    if len(text) > max_chars:
        text = text[: max_chars - 1] + "…"
    user = client.get_user(user_id)
    if user is None:
        # Not in cache (common for an owner who hasn't messaged the bot) — fetch.
        user = await client.fetch_user(user_id)
    sent = await user.send(text)
    return str(sent.id)


class DiscordAdapter(PlatformAdapter):
    name = "discord"
    max_chars = discord_style.MAX_CHARS
    workspace_is_global = True

    def __init__(self, *, cash_id: int, owner_id: int):
        self.cash_id = cash_id
        self.owner_id = owner_id

    def normalize(self, raw_event: Any) -> Optional[IncomingEvent]:
        """Map a discord.Message to an IncomingEvent. Returns None for bots."""
        message = raw_event
        if getattr(message.author, "bot", False):
            return None

        guild = getattr(message, "guild", None)
        channel = getattr(message, "channel", None)
        mentioned_ids = {u.id for u in getattr(message, "mentions", [])}

        return IncomingEvent(
            platform=self.name,
            platform_user_id=str(message.author.id),
            text=message.clean_content or "",
            workspace_id=str(guild.id) if guild else None,
            workspace_name=getattr(guild, "name", None),
            channel_id=str(channel.id) if channel else None,
            channel_name=getattr(channel, "name", None),
            display_name=message.author.display_name,
            handle=message.author.name,
            message_id=str(message.id),
            is_owner=(message.author.id == self.owner_id),
            is_direct=(guild is None),
            mentions_cash=(self.cash_id in mentioned_ids),
            mentions_owner=(self.owner_id in mentioned_ids),
            raw=message,
            metadata={"guild_id": getattr(guild, "id", None)},
        )

    async def send(self, event: IncomingEvent, message: OutgoingMessage) -> Optional[str]:
        """Reply to the originating discord.Message. Returns the sent id."""
        src = event.raw
        if src is None:
            logger.warning("[discord_adapter] no raw message to reply to")
            return None
        sent = await src.reply(self.clamp(message.text))
        return str(sent.id)
