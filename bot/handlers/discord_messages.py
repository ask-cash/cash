"""
discord_messages.py — Discord on_message dispatcher for Cash.

Step 1 scope:
  - Cash mentioned  → immediate reply via services.ai_brain.interpret_message
  - Suhail mentioned → log only (deferred-reply queue lands in Step 2)

Calendar / task / memory mutating actions are intentionally NOT executed from
Discord in this step — only the conversational `reply` field is sent. Action
dispatch (add_task, create_event, etc.) stays Telegram-only until we decide
who should be allowed to trigger it from Discord.
"""

import asyncio
import logging
from typing import Optional

import discord

from services.ai_brain import interpret_message
from services.memory import log_message

logger = logging.getLogger(__name__)


def _allowed_guild(guild: Optional[discord.Guild], allowed_ids: set[int]) -> bool:
    if not allowed_ids:
        return True  # empty allowlist = permit everything (dev mode)
    return bool(guild and guild.id in allowed_ids)


def _build_context_prefix(message: discord.Message, suhail_id: int) -> str:
    channel_name = getattr(message.channel, "name", "DM")
    if message.author.id == suhail_id:
        return f"[Discord channel #{channel_name}, message from Suhail himself]"
    author = message.author.display_name or message.author.name
    return (
        f"[Discord channel #{channel_name}, asked by @{author} who is NOT Suhail. "
        f"Be friendly and stay in Cash's voice, but do NOT reveal Suhail's "
        f"private tasks, schedule, trading rules, decisions, or memory. "
        f"Keep the reply short — two sentences max.]"
    )


async def _reply_as_cash(message: discord.Message, suhail_id: int) -> None:
    user_msg = message.clean_content or ""
    prefix = _build_context_prefix(message, suhail_id)
    prompt = f"{prefix}\n{user_msg}"

    log_message(
        "user",
        user_msg,
        metadata={
            "surface": "discord",
            "guild_id": getattr(message.guild, "id", None),
            "channel_id": message.channel.id,
            "channel_name": getattr(message.channel, "name", None),
            "author_id": message.author.id,
            "author_name": message.author.display_name,
            "message_id": message.id,
        },
    )

    try:
        async with message.channel.typing():
            result = await asyncio.to_thread(interpret_message, prompt)
    except Exception:
        logger.exception("ai_brain.interpret_message failed for discord message %s", message.id)
        await message.reply("hiss — my brain glitched. try again in a sec? 🐾")
        return

    reply = (result.get("reply") or "").strip() or "🐾"
    # Discord's hard limit is 2000 chars; leave headroom.
    if len(reply) > 1900:
        reply = reply[:1897] + "..."

    sent = await message.reply(reply)
    log_message(
        "assistant",
        reply,
        metadata={
            "surface": "discord",
            "channel_id": message.channel.id,
            "in_reply_to": message.id,
            "sent_message_id": sent.id,
        },
    )


async def handle_discord_message(
    message: discord.Message,
    *,
    cash_id: int,
    suhail_id: int,
    allowed_guild_ids: set[int],
) -> None:
    if message.author.bot:
        return
    if not _allowed_guild(message.guild, allowed_guild_ids):
        return

    mentioned_ids = {u.id for u in message.mentions}

    if cash_id in mentioned_ids:
        await _reply_as_cash(message, suhail_id)
        return

    if suhail_id in mentioned_ids:
        # Step 2 will enqueue a deferred reply here.
        logger.info(
            "[discord] Suhail mention detected (deferred reply not implemented yet) "
            "guild=%s channel=%s author=%s msg_id=%s",
            getattr(message.guild, "id", None),
            message.channel.id,
            message.author.id,
            message.id,
        )
