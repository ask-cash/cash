"""
discord_client.py — Cash's Discord presence.

Run as a separate process from the Telegram bot:
    python -m bot.discord_client

Required env vars:
    DISCORD_BOT_TOKEN          bot token from Discord developer portal
    DISCORD_CASH_USER_ID       the bot account's user id (snowflake)
    DISCORD_SUHAIL_USER_ID     Suhail's Discord user id (snowflake)
    DISCORD_ALLOWED_GUILD_IDS  comma-separated guild ids; empty = allow all
    DISCORD_PROXY_DELAY_MIN    minutes to wait before proxy reply (default 30)
    DISCORD_PROXY_DELAY_MAX    upper bound on the random delay (default 40)
"""

import datetime as dt
import logging
import os

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from discord import app_commands
from dotenv import load_dotenv

from bot.handlers.discord_commands import register as register_slash_commands
from bot.handlers.discord_messages import (
    DiscordContext,
    handle_discord_message,
    handle_raw_message_delete,
    handle_raw_reaction_add,
    schedule_proxy_job,
)
from services.discord_queue import DiscordQueue, STALE_FIRE_GRACE_SECONDS

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _parse_int_set(raw: str) -> set[int]:
    if not raw:
        return set()
    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            logger.warning("Ignoring invalid id in allowlist: %r", part)
    return out


async def _replay_pending(ctx: DiscordContext) -> None:
    """Re-schedule queue records that survived a restart.

    Records whose fire_at is older than the misfire grace window are dropped
    rather than fired late. APScheduler will fire anything still within the
    grace window immediately when the scheduler starts.
    """
    now = dt.datetime.now(dt.timezone.utc)
    grace = dt.timedelta(seconds=STALE_FIRE_GRACE_SECONDS)
    survived = 0
    dropped = 0
    for record in ctx.queue.pending():
        fire_at = dt.datetime.fromisoformat(record.fire_at)
        if fire_at < now - grace:
            await ctx.queue.mark_skipped(record.message_id, "stale-on-boot")
            dropped += 1
            continue
        schedule_proxy_job(ctx, record)
        survived += 1
    logger.info("[boot] replayed %d pending records (%d dropped as stale)", survived, dropped)


def main() -> None:
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise SystemExit("❌ DISCORD_BOT_TOKEN not set in .env")

    suhail_id = int(os.getenv("DISCORD_SUHAIL_USER_ID", "0"))
    cash_id = int(os.getenv("DISCORD_CASH_USER_ID", "0"))
    if not suhail_id or not cash_id:
        raise SystemExit("❌ Set DISCORD_SUHAIL_USER_ID and DISCORD_CASH_USER_ID in .env")

    allowed_guilds = _parse_int_set(os.getenv("DISCORD_ALLOWED_GUILD_IDS", ""))
    proxy_min = int(os.getenv("DISCORD_PROXY_DELAY_MIN", "30"))
    proxy_max = int(os.getenv("DISCORD_PROXY_DELAY_MAX", "40"))
    if proxy_min > proxy_max:
        raise SystemExit("❌ DISCORD_PROXY_DELAY_MIN must be ≤ DISCORD_PROXY_DELAY_MAX")

    intents = discord.Intents.default()
    intents.message_content = True   # privileged
    intents.members = True           # privileged
    # Reactions and message-delete come through default intents; raw events
    # work even for messages not in cache.

    client = discord.Client(intents=intents)
    tree = app_commands.CommandTree(client)
    queue = DiscordQueue()
    queue.load()

    scheduler = AsyncIOScheduler()
    ctx = DiscordContext(
        cash_id=cash_id,
        suhail_id=suhail_id,
        allowed_guild_ids=allowed_guilds,
        queue=queue,
        scheduler=scheduler,
        client=client,
        proxy_min_minutes=proxy_min,
        proxy_max_minutes=proxy_max,
    )

    register_slash_commands(tree, suhail_id=suhail_id)

    @client.event
    async def on_ready():
        bot_id = client.user.id if client.user else None
        logger.info(
            "Cash connected to Discord as %s (id=%s) in %d guilds",
            client.user, bot_id, len(client.guilds),
        )
        if bot_id and bot_id != cash_id:
            logger.warning(
                "DISCORD_CASH_USER_ID (%s) does not match logged-in bot id (%s). "
                "Update .env so mention detection works.",
                cash_id, bot_id,
            )
        if allowed_guilds:
            logger.info("Allowed guilds: %s", sorted(allowed_guilds))
        else:
            logger.warning("No DISCORD_ALLOWED_GUILD_IDS set — Cash will respond in every guild it joins.")

        if not scheduler.running:
            scheduler.start()
            logger.info("[boot] AsyncIOScheduler started (proxy delay %d–%d min)",
                        proxy_min, proxy_max)
            await _replay_pending(ctx)

        # Sync slash commands. Guild-scoped sync is instant; global takes ~1h.
        # We always have allowed_guilds in prod; fall back to global if empty.
        try:
            if allowed_guilds:
                for gid in allowed_guilds:
                    await tree.sync(guild=discord.Object(id=gid))
                logger.info("[boot] slash commands synced to %d guild(s)", len(allowed_guilds))
            else:
                await tree.sync()
                logger.info("[boot] slash commands synced globally (may take up to 1h to propagate)")
        except Exception:
            logger.exception("[boot] failed to sync slash commands — they may not appear")

    @client.event
    async def on_message(message: discord.Message):
        try:
            await handle_discord_message(message, ctx)
        except Exception:
            logger.exception("Unhandled error in on_message (msg_id=%s)", message.id)

    @client.event
    async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
        try:
            await handle_raw_reaction_add(payload, ctx)
        except Exception:
            logger.exception("Unhandled error in on_raw_reaction_add (msg_id=%s)", payload.message_id)

    @client.event
    async def on_raw_message_delete(payload: discord.RawMessageDeleteEvent):
        try:
            await handle_raw_message_delete(payload, ctx)
        except Exception:
            logger.exception("Unhandled error in on_raw_message_delete (msg_id=%s)", payload.message_id)

    client.run(token, log_handler=None)


if __name__ == "__main__":
    main()
