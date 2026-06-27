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
from services.composer import base as composer_base
from services.composer import discord as discord_style
from services.discord_queue import DiscordQueue, PendingReply, STALE_FIRE_GRACE_SECONDS
from services.discord_responder import fire_proxy_reply
from services.identity import people as identity_people
from services.memory import log_message
from services.onboarding import assistant as onboarding_assistant
from services.onboarding import profiles as onboarding_profiles
from services.onboarding import runtime as onboarding_runtime
from services.platforms import base as platform_pipeline
from services.platforms.discord_adapter import DiscordAdapter

logger = logging.getLogger(__name__)


@dataclass
class DiscordContext:
    cash_id: int
    owner_id: int
    allowed_guild_ids: set[int]
    queue: DiscordQueue
    scheduler: AsyncIOScheduler
    client: discord.Client
    proxy_min_minutes: int = 30
    proxy_max_minutes: int = 40
    adapter: Optional[DiscordAdapter] = None

    def get_adapter(self) -> DiscordAdapter:
        """Lazily build the platform adapter from this context's ids."""
        if self.adapter is None:
            self.adapter = DiscordAdapter(cash_id=self.cash_id, owner_id=self.owner_id)
        return self.adapter


def _allowed_guild(guild: Optional[discord.Guild], allowed_ids: set[int]) -> bool:
    if not allowed_ids:
        return True  # empty allowlist = dev mode
    return bool(guild and guild.id in allowed_ids)


def _proxy_job_id(message_id: int) -> str:
    return f"proxy:{message_id}"


# Single source of truth for Discord tone now lives in the composer layer so
# the immediate-reply and proxy-reply paths can't drift apart.
_DISCORD_STYLE = discord_style.STYLE


def _build_context_prefix(message: discord.Message, owner_id: int) -> str:
    channel_name = getattr(message.channel, "name", "DM")
    if message.author.id == owner_id:
        return f"[Discord channel #{channel_name}, from the owner. {_DISCORD_STYLE}]"
    display = message.author.display_name or message.author.name
    handle = message.author.name
    return (
        f"[Discord channel #{channel_name}. Asker: display_name='{display}', "
        f"username='@{handle}', user_id={message.author.id}. This is NOT the owner. "
        f"Be friendly and stay in Cash's voice, but do NOT reveal the owner's "
        f"private tasks, schedule, trading rules, decisions, or memory. "
        f"{_DISCORD_STYLE}]"
    )


# ---------------------------------------------------------------------------
# Cash-mention path (immediate)
# ---------------------------------------------------------------------------

async def _resolve_decision(
    message: discord.Message, ctx: DiscordContext, person_id: Optional[str],
) -> platform_pipeline.Decision:
    """Resolve the directive decision for this message via the shared pipeline.

    Identity resolve + incoming logging already happened upstream
    (handle_discord_message / _reply_as_cash), so this only runs the
    platform-agnostic directive resolution and maps it to a Decision. The same
    code path is what Slack/Teams will use — the hard rules can't drift.
    """
    event = ctx.get_adapter().normalize(message)
    if event is None:  # bot author — shouldn't happen on this path
        return platform_pipeline.Decision(action=platform_pipeline.ACT_REPLY, person_id=person_id)
    action = await asyncio.to_thread(platform_pipeline.resolve_directive, event, person_id)
    return platform_pipeline.decision_from_action(action, person_id)


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

    # Hard-rule resolution — runs BEFORE any LLM call, through the shared pipeline.
    decision = await _resolve_decision(message, ctx, person_id)

    if decision.is_silenced:
        logger.info(
            "[discord] ignored msg=%s author=%s (@%s) per directive=%s",
            message.id, message.author.display_name, message.author.name,
            decision.directive_id,
        )
        log_message(
            "assistant", "[silenced per ignore directive]",
            metadata={
                **base_meta,
                "in_reply_to": message.id,
                "outcome": "silent-by-directive",
                "directive_id": decision.directive_id,
            },
        )
        return

    if decision.action == platform_pipeline.ACT_AUTO_REPLY and decision.canned_text:
        text = ctx.get_adapter().clamp(decision.canned_text)
        sent = await message.reply(text)
        log_message(
            "assistant", text,
            metadata={
                **base_meta,
                "in_reply_to": message.id,
                "sent_message_id": sent.id,
                "outcome": "auto-replied",
                "directive_id": decision.directive_id,
            },
        )
        logger.info(
            "[discord] auto-replied msg=%s per directive=%s",
            message.id, decision.directive_id,
        )
        return

    # Reply path. Inject bounded per-person memory (summary or last N lines) plus
    # any soft hints (e.g. 'prioritize') so Cash answers in context.
    person_ctx = await asyncio.to_thread(
        composer_base.build_person_context, person_id, soft_hints=decision.soft_hints,
    )
    memory_block = composer_base.render_context_block(person_ctx)
    prompt = f"{_build_context_prefix(message, ctx.owner_id)}\n"
    if memory_block:
        prompt += f"{memory_block}\n"
    prompt += user_msg
    try:
        async with message.channel.typing():
            result = await asyncio.to_thread(interpret_message, prompt)
    except Exception:
        logger.exception("ai_brain.interpret_message failed for discord msg %s", message.id)
        await message.reply("Sorry, I hit an error on that one. Could you try again in a moment?")
        return

    reply = (result.get("reply") or "").strip() or "Sorry, I didn't catch that — could you rephrase?"
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
            "owner_id": ctx.owner_id,
        },
        id=_proxy_job_id(record.message_id),
        misfire_grace_time=STALE_FIRE_GRACE_SECONDS,
        replace_existing=True,
    )


async def _enqueue_owner_mention(
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

    # Direct messages (no guild) from non-owner users are the onboarding /
    # customer-assistant surface — handled before the guild allowlist, which
    # only governs server channels.
    if message.guild is None and message.author.id != ctx.owner_id:
        await _handle_direct_message(message, ctx)
        return

    if not _allowed_guild(message.guild, ctx.allowed_guild_ids):
        return

    # Identity layer: every non-bot author becomes a person row on first sight.
    # No-op for repeat senders other than refreshing last_seen / display_name.
    person_id = await _resolve_author_identity(message)

    # Cancellation signal: Suhail himself posted in this channel — anything
    # earlier-than-this-post is now considered "seen" and shouldn't proxy.
    if message.author.id == ctx.owner_id:
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

    if ctx.owner_id in mentioned_ids and message.author.id != ctx.owner_id:
        await _enqueue_owner_mention(message, ctx, person_id=person_id)


# ---------------------------------------------------------------------------
# Direct-message onboarding / customer assistant
# ---------------------------------------------------------------------------

async def _handle_direct_message(message: discord.Message, ctx: DiscordContext) -> None:
    """Onboard or assist a non-owner user who DMs Cash on Discord.

    Mirrors the Telegram non-owner path via the shared onboarding runtime, so
    a new user gets the same in-chat onboarding + secure setup link, and an
    active customer gets the scoped assistant (never the owner's private brain).
    """
    person_id = await _resolve_author_identity(message)
    text = message.clean_content or ""
    log_message("user", text, metadata={"surface": "discord", "person_id": person_id, "direct": True})

    from types import SimpleNamespace
    ev = SimpleNamespace(text=text, is_owner=False, is_direct=True)
    rr = await asyncio.to_thread(onboarding_runtime.route, ev, person_id)
    if rr.handled:
        await message.reply(rr.reply[:1900])
        log_message("assistant", rr.reply, metadata={"surface": "discord", "person_id": person_id, "outcome": "onboarding"})
        return

    profile = await asyncio.to_thread(onboarding_profiles.get_profile, person_id)
    if profile is None:
        await message.reply("One moment — let me get you set up.")
        return
    async with message.channel.typing():
        reply = await asyncio.to_thread(onboarding_assistant.customer_reply, profile, person_id, text)
    await message.reply(reply[:1900])
    log_message("assistant", reply, metadata={"surface": "discord", "person_id": person_id, "outcome": "customer-assistant"})


# ---------------------------------------------------------------------------
# Reaction & deletion cancellation
# ---------------------------------------------------------------------------

async def handle_raw_reaction_add(
    payload: discord.RawReactionActionEvent, ctx: DiscordContext
) -> None:
    """If Suhail reacts to a tracked mention, treat it as 'seen' and cancel."""
    if payload.user_id != ctx.owner_id:
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
