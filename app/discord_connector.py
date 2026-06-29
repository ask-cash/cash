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
from services.identity import linking as identity_linking
from services.identity import people as identity_people
from services.onboarding import links as signed_links
from services.platforms.discord_adapter import deliver as deliver_discord_dm
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


def _env_int(name: str) -> int:
    raw = os.getenv(name, "")
    return int(raw) if raw.strip().isdigit() else 0


def _env_guild_allowlist() -> set[int]:
    out: set[int] = set()
    for part in os.getenv("DISCORD_ALLOWED_GUILD_IDS", "").split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out


async def _consume_outbound(tenant_id: str, client: discord.Client, owner_id: int) -> None:
    """Drain this tenant's Discord outbound queue and DM via the live socket.

    The Redis pop is blocking, so it runs in a worker thread to keep the gateway
    event loop responsive. Targets: an explicit ``platform_user_id`` in the job,
    or ``to == "owner"`` resolved against this tenant's configured owner id.
    """
    if not settings.redis_url:
        logger.info("[%s] no REDIS_URL — Discord outbound delivery disabled", tenant_id)
        return
    await client.wait_until_ready()
    logger.info("[%s] outbound consumer ready", tenant_id)
    while not client.is_closed():
        try:
            job = await asyncio.to_thread(queue.dequeue_outbound, "discord", tenant_id, 5)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[%s] outbound dequeue failed", tenant_id)
            await asyncio.sleep(5)
            continue
        if not job:
            continue

        payload = job.get("payload", {}) or {}
        idem = payload.get("idempotency_key")
        if idem and not await asyncio.to_thread(queue.claim_idempotency, idem):
            logger.info("[%s] outbound %s already delivered — skipping", tenant_id, idem)
            continue

        explicit = payload.get("platform_user_id")
        target = int(explicit) if str(explicit).isdigit() else (owner_id if payload.get("to") == "owner" else 0)
        if not target:
            logger.warning("[%s] outbound job has no resolvable target: %s", tenant_id, payload.get("to"))
            continue
        try:
            await deliver_discord_dm(client, target, payload.get("text", ""))
            logger.info("[%s] delivered outbound DM to %s", tenant_id, target)
        except Exception:
            logger.exception("[%s] outbound delivery to %s failed", tenant_id, target)


def _link_discord_account(tenant_id: str, primary_person_id: str, author_id, display_name, handle) -> str:
    """Fold the DMer's Discord person into the dashboard person. Runs in a worker
    thread, so it sets its own tenant context (contextvars don't cross threads).
    Returns a status: 'linked' | 'already' | 'unknown_primary'.
    """
    with tenant_context(tenant_id):
        discord_pid = identity_people.resolve(
            platform="discord", platform_user_id=str(author_id),
            display_name=display_name, handle=handle,
        )
        if discord_pid == primary_person_id:
            return "already"
        try:
            identity_linking.link_identities(primary_person_id, discord_pid)
        except ValueError:
            return "unknown_primary"
        return "linked"


async def _handle_link_command(message: "discord.Message", tenant_id: str) -> None:
    """Handle a DM of the form '/link <phrase>' from the dashboard connect flow."""
    content = (message.content or "").strip()
    phrase = content.split(None, 1)[1].strip() if " " in content else ""
    logger.info("[%s] /link from %s — phrase valid=%s", tenant_id, message.author.id, bool(signed_links.verify_token(phrase)))
    payload = signed_links.verify_token(phrase)
    if not payload:
        await message.channel.send(
            "That link code is invalid or expired — open your Cash dashboard and grab a fresh one."
        )
        return
    if payload.get("tid", "default") != tenant_id:
        await message.channel.send("That link code isn't for this Cash account.")
        return
    status = await asyncio.to_thread(
        _link_discord_account, tenant_id, payload["pid"],
        message.author.id, message.author.display_name, message.author.name,
    )
    if status == "linked":
        await message.channel.send("✅ Linked! Your Discord and your other platforms now share one Cash memory.")
    elif status == "already":
        await message.channel.send("✅ Your Discord is already linked.")
    else:
        await message.channel.send("I couldn't complete the link — generate a fresh code from your dashboard and try again.")


async def _run_tenant_client(tenant_id: str, token: str, scheduler: AsyncIOScheduler) -> None:
    with tenant_context(tenant_id):
        # Per-tenant vault values win; fall back to .env so a single-tenant local
        # run works straight from .env (DISCORD_CASH_USER_ID / DISCORD_OWNER_USER_ID /
        # *_ALLOWED_GUILD_IDS) with no DB onboarding required.
        cash_id = _int_secret(tenant_id, "discord_cash_user_id") or _env_int("DISCORD_CASH_USER_ID")
        owner_id = (
            _int_secret(tenant_id, "discord_owner_user_id")
            or _env_int("DISCORD_OWNER_USER_ID")
            or _env_int("DISCORD_SUHAIL_USER_ID")  # legacy name, kept for back-compat
        )
        allowed_guilds = _guild_allowlist(tenant_id) or _env_guild_allowlist()

    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True

    client = discord.Client(intents=intents)
    pending_path = os.path.join("user_data", "tenants", tenant_id, "discord_pending.json")
    q = DiscordQueue(path=pending_path)
    q.load()

    ctx = DiscordContext(
        cash_id=cash_id,
        owner_id=owner_id,
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
                # Diagnostic: log inbound DMs so we can see content + intents.
                if message.guild is None and not message.author.bot:
                    logger.info(
                        "[%s] DM from %s (id=%s): %r",
                        tenant_id, message.author, message.author.id, (message.content or "")[:80],
                    )
                # Dashboard "connect Discord" flow: a DM of "/link <phrase>" links
                # this Discord account to the dashboard person. Handle before the
                # normal proxy/identity path. Accept a leading slash or not.
                content = (message.content or "").strip()
                if (
                    message.guild is None
                    and not message.author.bot
                    and (content.startswith("/link ") or content.startswith("link "))
                ):
                    await _handle_link_command(message, tenant_id)
                    return
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

    outbound_task = asyncio.create_task(_consume_outbound(tenant_id, client, owner_id))
    try:
        await client.start(token)
    except Exception:
        logger.exception("[%s] discord client crashed", tenant_id)
    finally:
        outbound_task.cancel()
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

    # Env-based single-tenant bootstrap: if DISCORD_BOT_TOKEN is set, run that
    # bot for the default tenant straight from .env — no DB onboarding needed.
    # This is the local "take the bot from .env" path; the env bot is
    # authoritative for the default tenant (any DB row for it is skipped).
    env_token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    env_tenant = settings.default_tenant_id
    if env_token and _owns(env_tenant, all_ids + [env_tenant]):
        logger.info("[%s] starting discord bot from .env (DISCORD_BOT_TOKEN)", env_tenant)
        tasks.append(asyncio.create_task(_run_tenant_client(env_tenant, env_token, scheduler)))

    for bot in mine:
        if env_token and bot.tenant_id == env_tenant:
            continue  # env bot already covers the default tenant
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
