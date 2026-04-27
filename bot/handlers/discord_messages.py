"""
discord_messages.py — Discord event dispatchers for Cash.

Step 1: immediate reply when Cash is mentioned.
Step 2: deferred reply when Suhail is mentioned, with auto-cancellation when
        Suhail posts in the channel, reacts to the mention, or the mention is
        deleted.

Calendar / task / memory mutating actions are intentionally NOT executed from
Discord — only the conversational `reply` field from ai_brain is sent.
"""

import asyncio
import datetime as dt
import logging
import random
from dataclasses import dataclass, field
from typing import Optional

import discord
from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from services.ai_brain import interpret_message
from services.discord_queue import DiscordQueue, PendingReply, STALE_FIRE_GRACE_SECONDS
from services.discord_responder import fire_proxy_reply
from services.memory import log_message

logger = logging.getLogger(__name__)


@dataclass
class DiscordContext:
    cash_id: int
    suhail_id: int
    allowed_guild_ids: set[int]
    queue: DiscordQueue
    scheduler: AsyncIOScheduler
    client: discord.Client
    proxy_min_minutes: int = 30
    proxy_max_minutes: int = 40


def _allowed_guild(guild: Optional[discord.Guild], allowed_ids: set[int]) -> bool:
    if not allowed_ids:
        return True  # empty allowlist = dev mode
    return bool(guild and guild.id in allowed_ids)


def _proxy_job_id(message_id: int) -> str:
    return f"proxy:{message_id}"


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


# ---------------------------------------------------------------------------
# Cash-mention path (immediate)
# ---------------------------------------------------------------------------

async def _reply_as_cash(message: discord.Message, ctx: DiscordContext) -> None:
    user_msg = message.clean_content or ""
    prompt = f"{_build_context_prefix(message, ctx.suhail_id)}\n{user_msg}"

    log_message(
        "user", user_msg,
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
        logger.exception("ai_brain.interpret_message failed for discord msg %s", message.id)
        await message.reply("hiss — my brain glitched. try again in a sec? 🐾")
        return

    reply = (result.get("reply") or "").strip() or "🐾"
    if len(reply) > 1900:
        reply = reply[:1897] + "..."

    sent = await message.reply(reply)
    log_message(
        "assistant", reply,
        metadata={
            "surface": "discord",
            "channel_id": message.channel.id,
            "in_reply_to": message.id,
            "sent_message_id": sent.id,
        },
    )


# ---------------------------------------------------------------------------
# Suhail-mention path (deferred)
# ---------------------------------------------------------------------------

def schedule_proxy_job(ctx: DiscordContext, record: PendingReply) -> None:
    """Schedule the proxy reply for a queued record."""
    fire_at = dt.datetime.fromisoformat(record.fire_at)
    ctx.scheduler.add_job(
        fire_proxy_reply,
        trigger=DateTrigger(run_date=fire_at),
        kwargs={
            "message_id": record.message_id,
            "queue": ctx.queue,
            "client": ctx.client,
            "suhail_id": ctx.suhail_id,
        },
        id=_proxy_job_id(record.message_id),
        misfire_grace_time=STALE_FIRE_GRACE_SECONDS,
        replace_existing=True,
    )


async def _enqueue_suhail_mention(message: discord.Message, ctx: DiscordContext) -> None:
    delay_minutes = random.randint(ctx.proxy_min_minutes, ctx.proxy_max_minutes)
    now = dt.datetime.now(dt.timezone.utc)
    fire_at = now + dt.timedelta(minutes=delay_minutes)

    record = PendingReply(
        message_id=message.id,
        channel_id=message.channel.id,
        guild_id=getattr(message.guild, "id", None),
        mentioner_id=message.author.id,
        mentioner_name=message.author.display_name or message.author.name,
        content=message.clean_content or "",
        created_at=now.isoformat(),
        fire_at=fire_at.isoformat(),
    )
    await ctx.queue.enqueue(record)
    schedule_proxy_job(ctx, record)
    logger.info(
        "[discord] queued proxy reply for msg=%s fire_at=%s (in %d min)",
        message.id, fire_at.isoformat(), delay_minutes,
    )


async def _cancel_proxy_job(ctx: DiscordContext, message_id: int) -> None:
    try:
        ctx.scheduler.remove_job(_proxy_job_id(message_id))
    except JobLookupError:
        pass


# ---------------------------------------------------------------------------
# on_message
# ---------------------------------------------------------------------------

async def handle_discord_message(message: discord.Message, ctx: DiscordContext) -> None:
    if message.author.bot:
        return
    if not _allowed_guild(message.guild, ctx.allowed_guild_ids):
        return

    # Cancellation signal: Suhail himself posted in this channel — anything
    # earlier-than-this-post is now considered "seen" and shouldn't proxy.
    if message.author.id == ctx.suhail_id:
        cancelled = await ctx.queue.cancel_in_channel_before(
            channel_id=message.channel.id,
            before=message.created_at,
            reason="suhail-posted-in-channel",
        )
        for r in cancelled:
            await _cancel_proxy_job(ctx, r.message_id)

    mentioned_ids = {u.id for u in message.mentions}

    if ctx.cash_id in mentioned_ids:
        await _reply_as_cash(message, ctx)
        return

    if ctx.suhail_id in mentioned_ids and message.author.id != ctx.suhail_id:
        await _enqueue_suhail_mention(message, ctx)


# ---------------------------------------------------------------------------
# Reaction & deletion cancellation
# ---------------------------------------------------------------------------

async def handle_raw_reaction_add(
    payload: discord.RawReactionActionEvent, ctx: DiscordContext
) -> None:
    """If Suhail reacts to a tracked mention, treat it as 'seen' and cancel."""
    if payload.user_id != ctx.suhail_id:
        return
    record = ctx.queue.get(payload.message_id)
    if record is None or record.status != "pending":
        return
    await ctx.queue.cancel(payload.message_id, "suhail-reacted")
    await _cancel_proxy_job(ctx, payload.message_id)


async def handle_raw_message_delete(
    payload: discord.RawMessageDeleteEvent, ctx: DiscordContext
) -> None:
    """If the original mention is deleted, drop the pending record."""
    record = ctx.queue.get(payload.message_id)
    if record is None or record.status != "pending":
        return
    await ctx.queue.cancel(payload.message_id, "original-deleted")
    await _cancel_proxy_job(ctx, payload.message_id)
