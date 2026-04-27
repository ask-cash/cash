"""
discord_responder.py — Fire a proxy reply for a pending mention.

Step 2 scope: late-cancellation re-check + placeholder message. Step 3 plugs
in the availability service; Step 4 plugs in the LLM-composed reply.

The function returns the sent message (or None if skipped) so the caller can
mark the queue record accordingly.
"""

import datetime as dt
import logging
from typing import Optional

import discord

from services.discord_queue import DiscordQueue, PendingReply

logger = logging.getLogger(__name__)

PLACEHOLDER_REPLY = (
    "🐾 [Cash placeholder — Step 2] Suhail hasn't responded; the calendar-aware "
    "proxy reply will land in Step 3."
)


async def _suhail_active_in_channel_since(
    client: discord.Client, channel_id: int, suhail_id: int, since: dt.datetime
) -> bool:
    """Did Suhail post anything in this channel after `since`? Late safety net."""
    channel = client.get_channel(channel_id)
    if channel is None:
        try:
            channel = await client.fetch_channel(channel_id)
        except Exception:
            logger.exception("Could not fetch channel %s for late-check", channel_id)
            return False
    try:
        async for msg in channel.history(limit=50, after=since):
            if msg.author.id == suhail_id:
                return True
    except Exception:
        logger.exception("history() failed for channel %s", channel_id)
    return False


async def fire_proxy_reply(
    *,
    message_id: int,
    queue: DiscordQueue,
    client: discord.Client,
    suhail_id: int,
) -> None:
    """Scheduler job entrypoint. Re-checks state, then sends or skips."""
    record = queue.get(message_id)
    if record is None:
        logger.info("[responder] no record for %s — nothing to fire", message_id)
        return
    if record.status != "pending":
        logger.info("[responder] record %s status=%s — skipping fire", message_id, record.status)
        return

    created_at = dt.datetime.fromisoformat(record.created_at)
    if await _suhail_active_in_channel_since(client, record.channel_id, suhail_id, created_at):
        await queue.cancel(message_id, "suhail-active-late-check")
        return

    channel = client.get_channel(record.channel_id)
    if channel is None:
        try:
            channel = await client.fetch_channel(record.channel_id)
        except Exception:
            logger.exception("Could not fetch channel %s to send proxy reply", record.channel_id)
            await queue.mark_skipped(message_id, "channel-unreachable")
            return

    try:
        original = await channel.fetch_message(message_id)
    except discord.NotFound:
        logger.info("[responder] original message %s deleted — skipping", message_id)
        await queue.mark_skipped(message_id, "original-deleted")
        return
    except Exception:
        logger.exception("[responder] fetch_message failed for %s", message_id)
        await queue.mark_skipped(message_id, "fetch-failed")
        return

    try:
        await original.reply(_compose(record))
    except Exception:
        logger.exception("[responder] failed to send proxy reply for %s", message_id)
        await queue.mark_skipped(message_id, "send-failed")
        return

    await queue.mark_sent(message_id)
    logger.info("[responder] sent proxy reply for %s", message_id)


def _compose(record: PendingReply) -> str:
    # Step 4 will replace this with the LLM-composed reply.
    return PLACEHOLDER_REPLY
