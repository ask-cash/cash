"""
main.py — Entry point for the Personal AI Assistant Telegram bot.
"""

import asyncio
import os
import logging
import datetime as dt

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application

from services.user_profile import load_profile
from bot.handlers.commands import on_google_connected
from bot.jobs import get_cal, get_gmail
from services import oauth_server
from bot.jobs import (
    scheduled_directive_expiry,
    scheduled_email_check,
    scheduled_evening_summary,
    scheduled_meeting_check,
    scheduled_morning_briefing,
    scheduled_summary_rollup,
    scheduled_trading_reminder,
)

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OWNER_ID = int(os.getenv("YOUR_TELEGRAM_USER_ID", "0"))


async def _post_init(app: Application):
    """Wire OAuth server into the running event loop and notify owner if disconnected."""
    redirect_uri = os.getenv("OAUTH_REDIRECT_URI", "")
    port = int(os.getenv("OAUTH_SERVER_PORT", "8080"))

    on_google_connected._app = app  # type: ignore[attr-defined]

    if redirect_uri:
        oauth_server.configure(
            redirect_uri=redirect_uri,
            on_success=on_google_connected,
            loop=asyncio.get_running_loop(),
            creds_path=os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json"),
            token_path=os.getenv("GOOGLE_TOKEN_PATH", "token.json"),
        )
        try:
            oauth_server.start_oauth_server(port)
        except Exception as e:
            logger.error("Could not start OAuth server on :%d — %s", port, e)
    else:
        logger.warning("OAUTH_REDIRECT_URI not set — /connect_google will be unavailable")

    # Probe connectors on boot; DM owner which ones need reconnecting.
    if OWNER_ID:
        missing = []
        try:
            cal = get_cal()
            if not cal.google:
                missing.append(("Google Calendar", "/connect_google"))
            if os.getenv("OUTLOOK_CLIENT_ID") and not cal.outlook:
                missing.append(("Outlook", "/connect_outlook"))
        except Exception as e:
            logger.error("Startup calendar probe failed: %s", e)
        try:
            if not get_gmail():
                missing.append(("Gmail", "/connect_gmail"))
        except Exception as e:
            logger.error("Startup gmail probe failed: %s", e)

        if missing:
            lines = ["😿 Some connectors need attention:"]
            for name, cmd in missing:
                lines.append(f"  • {name} — send {cmd}")
            await app.bot.send_message(chat_id=OWNER_ID, text="\n".join(lines))


def main():
    if not BOT_TOKEN:
        print("❌ Set TELEGRAM_BOT_TOKEN in .env")
        return

    app = Application.builder().token(BOT_TOKEN).post_init(_post_init).build()

    # Register the shared handler set (same wiring the multi-tenant worker uses).
    from bot.app_factory import register_handlers
    register_handlers(app, owner_id=OWNER_ID)

    # Scheduled jobs
    profile = load_profile()
    wake = profile.get("wake_time", "06:30").split(":")
    trade_review = profile.get("trading", {}).get("pre_market_review_time", "08:45").split(":")
    sleep = profile.get("sleep_time", "23:00").split(":")

    job_queue = app.job_queue
    job_queue.run_daily(
        scheduled_morning_briefing,
        time=dt.time(int(wake[0]), int(wake[1])),
        name="morning_briefing",
    )
    job_queue.run_daily(
        scheduled_trading_reminder,
        time=dt.time(int(trade_review[0]), int(trade_review[1])),
        days=(0, 1, 2, 3, 4),
        name="trading_reminder",
    )
    job_queue.run_repeating(
        scheduled_meeting_check,
        interval=1800,
        first=10,
        name="meeting_check",
    )
    job_queue.run_daily(
        scheduled_evening_summary,
        time=dt.time(int(sleep[0]), int(sleep[1])),
        name="evening_summary",
    )

    # Email check — every 30 minutes
    email_check_interval = int(os.getenv("EMAIL_CHECK_INTERVAL_SECONDS", "1800"))
    job_queue.run_repeating(
        scheduled_email_check,
        interval=email_check_interval,
        first=30,
        name="email_check",
    )

    # Directive lifecycle (Step 7) — runs early morning local time.
    job_queue.run_daily(
        scheduled_directive_expiry,
        time=dt.time(3, 0),
        name="directive_expiry",
    )
    job_queue.run_daily(
        scheduled_summary_rollup,
        time=dt.time(3, 30),
        name="summary_rollup",
    )

    logger.info("🚀 Bot is running with memory + multi-calendar!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
