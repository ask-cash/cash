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
from services.directives import resolve as directives_resolve
from services.directives import store as directives_store
from services.discord_queue import DiscordQueue, PendingReply, STALE_FIRE_GRACE_SECONDS
from services.discord_responder import fire_proxy_reply
from services.identity import people as identity_people
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


_DISCORD_STYLE = (
    "Discord style: keep it concise — at most 2 short sentences, ideally one. "
    "No headers, no bullet lists, no markdown code blocks unless explicitly asked. "
    "Match the asker's language: if they write Hinglish (Hindi-English mix in "
    "Latin letters, e.g. 'kaise ho', 'kal milte hain', 'bhai chill'), reply in "
    "Hinglish too. If they write English, reply in English. Don't translate to "
    "formal Hindi or Devanagari."
)


def _build_context_prefix(message: discord.Message, suhail_id: int) -> str:
    channel_name = getattr(message.channel, "name", "DM")
    if message.author.id == suhail_id:
        return f"[Discord channel #{channel_name}, from Suhail. {_DISCORD_STYLE}]"
    display = message.author.display_name or message.author.name
    handle = message.author.name
    return (
        f"[Discord channel #{channel_name}. Asker: display_name='{display}', "
        f"username='@{handle}', user_id={message.author.id}. This is NOT Suhail. "
        f"Be friendly and stay in Cash's voice, but do NOT reveal Suhail's "
        f"private tasks, schedule, trading rules, decisions, or memory. "
        f"{_DISCORD_STYLE}]"
    )


# ---------------------------------------------------------------------------
# Cash-mention path (immediate)
# ---------------------------------------------------------------------------

async def _resolve_directive_for_message(
    message: discord.Message, person_id: Optional[str],
) -> directives_resolve.EffectiveAction:
    """Look up active directives and resolve them against this message's event."""
    if not person_id:
        return directives_resolve.EffectiveAction(action="reply")
    try:
        directives = await asyncio.to_thread(
            directives_store.list_active_for_person, person_id,
        )
    except Exception:
        logger.exception("[directives] list_active failed for person=%s — defaulting to reply", person_id)
        return directives_resolve.EffectiveAction(action="reply")

    event = directives_resolve.Event(
        platform="discord",
        workspace_id=str(message.guild.id) if message.guild else None,
        channel_id=str(message.channel.id),
        person_id=person_id,
    )
    return directives_resolve.effective_action(event, directives)


async def _reply_as_cash(
    message: discord.Message, ctx: DiscordContext, *, person_id: Optional[str] = None,
) -> None:
    user_msg = message.clean_content or ""

    base_meta = {
        "surface": "discord",
        "person_id": person_id,
        "guild_id": getattr(message.guild, "id", None),
        "channel_id": message.channel.id,
        "channel_name": getattr(message.channel, "name", None),
        "author_id": message.author.id,
        "author_name": message.author.display_name,
        "message_id": message.id,
    }

    log_message("user", user_msg, metadata=base_meta)

    # Directive resolution — runs BEFORE any LLM call.
    action = await _resolve_directive_for_message(message, person_id)

    if action.action == "ignore":
        logger.info(
            "[discord] ignored msg=%s author=%s (@%s) per directive=%s",
            message.id, message.author.display_name, message.author.name,
            action.chosen_directive_id,
        )
        log_message(
            "assistant", "[silenced per ignore directive]",
            metadata={
                **base_meta,
                "in_reply_to": message.id,
                "outcome": "silent-by-directive",
                "directive_id": action.chosen_directive_id,
            },
        )
        return

    if action.action == "auto_reply":
        canned = (action.payload.get("text") or "").strip()
        if canned:
            text = canned[:1900]
            sent = await message.reply(text)
            log_message(
                "assistant", text,
                metadata={
                    **base_meta,
                    "in_reply_to": message.id,
                    "sent_message_id": sent.id,
                    "outcome": "auto-replied",
                    "directive_id": action.chosen_directive_id,
                },
            )
            logger.info(
                "[discord] auto-replied msg=%s per directive=%s",
                message.id, action.chosen_directive_id,
            )
            return
        logger.warning(
            "[discord] auto_reply directive %s missing payload.text — falling through to LLM",
            action.chosen_directive_id,
        )

    # No matching directive → existing LLM flow.
    prompt = f"{_build_context_prefix(message, ctx.suhail_id)}\n{user_msg}"
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
            **base_meta,
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


async def _enqueue_suhail_mention(
    message: discord.Message, ctx: DiscordContext, *, person_id: Optional[str] = None,
) -> None:
    delay_minutes = random.randint(ctx.proxy_min_minutes, ctx.proxy_max_minutes)
    now = dt.datetime.now(dt.timezone.utc)
    fire_at = now + dt.timedelta(minutes=delay_minutes)

    record = PendingReply(
        message_id=message.id,
        channel_id=message.channel.id,
        guild_id=getattr(message.guild, "id", None),
        mentioner_id=message.author.id,
        mentioner_name=message.author.display_name or message.author.name,
        mentioner_username=message.author.name,
        mentioner_person_id=person_id or "",
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
# Identity resolution (best-effort; never blocks message flow)
# ---------------------------------------------------------------------------

async def _resolve_author_identity(message: discord.Message) -> Optional[str]:
    """Auto-create or update the person row for this message's author.

    Best-effort — identity errors are logged but never fail the message flow.
    Discord user IDs are global, so workspace_id is informational only at the
    application layer (see services.identity.people).
    """
    try:
        return await asyncio.to_thread(
            identity_people.resolve,
            platform="discord",
            platform_user_id=str(message.author.id),
            workspace_id=str(message.guild.id) if message.guild else None,
            display_name=message.author.display_name,
            handle=message.author.name,
        )
    except Exception:
        logger.exception(
            "[identity] resolve failed for discord msg=%s author=%s — continuing",
            message.id, message.author.id,
        )
        return None


# ---------------------------------------------------------------------------
# on_message
# ---------------------------------------------------------------------------

async def handle_discord_message(message: discord.Message, ctx: DiscordContext) -> None:
    if message.author.bot:
        return
    if not _allowed_guild(message.guild, ctx.allowed_guild_ids):
        return

    # Identity layer: every non-bot author becomes a person row on first sight.
    # No-op for repeat senders other than refreshing last_seen / display_name.
    person_id = await _resolve_author_identity(message)

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
        await _reply_as_cash(message, ctx, person_id=person_id)
        return

    if ctx.suhail_id in mentioned_ids and message.author.id != ctx.suhail_id:
        await _enqueue_suhail_mention(message, ctx, person_id=person_id)


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
