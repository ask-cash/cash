"""
discord_client.py — Cash's Discord presence.

Run as a separate process from the Telegram bot:
    python -m bot.discord_client

Required env vars:
    DISCORD_BOT_TOKEN          bot token from Discord developer portal
    DISCORD_CASH_USER_ID       the bot account's user id (snowflake)
    DISCORD_SUHAIL_USER_ID     Suhail's Discord user id (snowflake)
    DISCORD_ALLOWED_GUILD_IDS  comma-separated guild ids; empty = allow all
"""

import logging
import os

import discord
from dotenv import load_dotenv

from bot.handlers.discord_messages import handle_discord_message

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


def main() -> None:
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise SystemExit("❌ DISCORD_BOT_TOKEN not set in .env")

    suhail_id = int(os.getenv("DISCORD_SUHAIL_USER_ID", "0"))
    cash_id = int(os.getenv("DISCORD_CASH_USER_ID", "0"))
    if not suhail_id or not cash_id:
        raise SystemExit(
            "❌ Set DISCORD_SUHAIL_USER_ID and DISCORD_CASH_USER_ID in .env"
        )

    allowed_guilds = _parse_int_set(os.getenv("DISCORD_ALLOWED_GUILD_IDS", ""))

    intents = discord.Intents.default()
    intents.message_content = True  # privileged — enable in Developer Portal
    intents.members = True          # privileged — enable in Developer Portal

    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        bot_id = client.user.id if client.user else None
        logger.info(
            "🐾 Cash connected to Discord as %s (id=%s) in %d guilds",
            client.user, bot_id, len(client.guilds),
        )
        if bot_id and bot_id != cash_id:
            logger.warning(
                "DISCORD_CASH_USER_ID (%s) does not match the logged-in bot id (%s). "
                "Update .env so mention detection works.",
                cash_id, bot_id,
            )
        if allowed_guilds:
            logger.info("Allowed guilds: %s", sorted(allowed_guilds))
        else:
            logger.warning("No DISCORD_ALLOWED_GUILD_IDS set — Cash will respond in every guild it joins.")

    @client.event
    async def on_message(message: discord.Message):
        try:
            await handle_discord_message(
                message,
                cash_id=cash_id,
                suhail_id=suhail_id,
                allowed_guild_ids=allowed_guilds,
            )
        except Exception:
            logger.exception("Unhandled error in on_message (msg_id=%s)", message.id)

    client.run(token, log_handler=None)


if __name__ == "__main__":
    main()
