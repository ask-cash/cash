"""
discord_connector.py — Sharded, multi-tenant Discord gateway pool.

Discord delivers messages over a persistent gateway websocket per bot token,
so it can't be a stateless webhook like Telegram. This connector runs as a
StatefulSet where each pod (ordinal = CONNECTOR_SHARD_INDEX) owns a fixed slice
of the tenants' Discord bots, opening one client per tenant in its slice.

Every gateway event is handled inside that tenant's context (so identity,
memory and the proxy queue resolve to the right tenant) and a lightweight
event is also pushed onto the job queue for the worker to learn from
asynchronously. Replies are sent on the live socket this pod owns.

Scale out by raising the StatefulSet replica count + CONNECTOR_SHARD_TOTAL.
"""

from __future__ import annotations

import asyncio
import logging
import os

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.observability import CONNECTOR_SOCKETS, configure_logging
from bot.handlers.discord_messages import (
    DiscordContext,
    handle_discord_message,
    handle_raw_message_delete,
    handle_raw_reaction_add,
)
from services import queue
from services import secrets as secret_vault
from services import tenant_registry
from services.config import settings
from services.db import bootstrap
from services.discord_queue import DiscordQueue
from services.tenancy import system_context, tenant_context

configure_logging()
logger = logging.getLogger(__name__)


def _owns(tenant_id: str, all_tenant_ids: list[str]) -> bool:
    """Stable shard assignment: this pod owns tenant if its index maps here."""
    try:
        idx = sorted(all_tenant_ids).index(tenant_id)
    except ValueError:
        return False
    return idx % max(settings.connector_shard_total, 1) == settings.connector_shard_index


def _int_secret(tenant_id: str, name: str) -> int:
    raw = secret_vault.get_secret(name, tenant_id=tenant_id)
    return int(raw) if raw and raw.isdigit() else 0


def _guild_allowlist(tenant_id: str) -> set[int]:
    raw = secret_vault.get_secret("discord_allowed_guild_ids", tenant_id=tenant_id) or ""
    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out


async def _run_tenant_client(tenant_id: str, token: str, scheduler: AsyncIOScheduler) -> None:
    with tenant_context(tenant_id):
        cash_id = _int_secret(tenant_id, "discord_cash_user_id")
        owner_id = _int_secret(tenant_id, "discord_owner_user_id")
        allowed_guilds = _guild_allowlist(tenant_id)

    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True

    client = discord.Client(intents=intents)
    pending_path = os.path.join("user_data", "tenants", tenant_id, "discord_pending.json")
    q = DiscordQueue(path=pending_path)
    q.load()

    ctx = DiscordContext(
        cash_id=cash_id,
        suhail_id=owner_id,
        allowed_guild_ids=allowed_guilds,
        queue=q,
        scheduler=scheduler,
        client=client,
        proxy_min_minutes=int(os.getenv("DISCORD_PROXY_DELAY_MIN", "30")),
        proxy_max_minutes=int(os.getenv("DISCORD_PROXY_DELAY_MAX", "40")),
    )

    @client.event
    async def on_ready():
        CONNECTOR_SOCKETS.inc()
        logger.info("[%s] connected to Discord as %s", tenant_id, client.user)

    @client.event
    async def on_message(message: discord.Message):
        with tenant_context(tenant_id):
            try:
                await handle_discord_message(message, ctx)
                if not message.author.bot:
                    queue.enqueue(queue.DISCORD_EVENT, tenant_id, {
                        "content": message.content,
                        "author_name": str(message.author),
                        "channel_id": message.channel.id,
                    })
            except Exception:
                logger.exception("[%s] on_message failed (msg=%s)", tenant_id, message.id)

    @client.event
    async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
        with tenant_context(tenant_id):
            try:
                await handle_raw_reaction_add(payload, ctx)
            except Exception:
                logger.exception("[%s] reaction handler failed", tenant_id)

    @client.event
    async def on_raw_message_delete(payload: discord.RawMessageDeleteEvent):
        with tenant_context(tenant_id):
            try:
                await handle_raw_message_delete(payload, ctx)
            except Exception:
                logger.exception("[%s] delete handler failed", tenant_id)

    try:
        await client.start(token)
    except Exception:
        logger.exception("[%s] discord client crashed", tenant_id)
    finally:
        CONNECTOR_SOCKETS.dec()


async def run() -> None:
    bootstrap()
    with system_context():
        bots = tenant_registry.list_bots("discord")
    all_ids = [b.tenant_id for b in bots]
    mine = [b for b in bots if _owns(b.tenant_id, all_ids)]
    logger.info(
        "connector shard %d/%d owns %d of %d discord tenants",
        settings.connector_shard_index, settings.connector_shard_total,
        len(mine), len(bots),
    )

    scheduler = AsyncIOScheduler()
    scheduler.start()

    tasks = []
    for bot in mine:
        with system_context():
            token = tenant_registry.get_bot_token(bot.tenant_id, "discord")
        if not token:
            logger.warning("no discord token for tenant %s", bot.tenant_id)
            continue
        tasks.append(asyncio.create_task(_run_tenant_client(bot.tenant_id, token, scheduler)))

    if not tasks:
        logger.warning("no discord tenants assigned to this shard — idling")
        while True:
            await asyncio.sleep(60)
    await asyncio.gather(*tasks)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
