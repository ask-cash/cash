"""
main.py — Entry point for the Personal AI Assistant Telegram bot.
"""

import asyncio
import os
import logging
import datetime as dt

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from services.user_profile import load_profile
from bot.handlers.commands import (
    cmd_start,
    cmd_briefing,
    cmd_tasks,
    cmd_done,
    cmd_add,
    cmd_schedule,
    cmd_conflicts,
    cmd_rules,
    cmd_decisions,
    cmd_memory,
    cmd_calendars,
    cmd_settings,
    cmd_emails,
    cmd_email_detail,
    cmd_email_prefs,
    cmd_connect_google,
    cmd_connect_gmail,
    cmd_connect_outlook,
    on_google_connected,
    handle_email_feedback,
)
from bot.handlers.messages import handle_message
from bot.handlers.files import handle_file
from bot.jobs import get_cal, get_gmail
from services import oauth_server
from bot.jobs import (
    scheduled_morning_briefing,
    scheduled_trading_reminder,
    scheduled_meeting_check,
    scheduled_evening_summary,
    scheduled_email_check,
)

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OWNER_ID = int(os.getenv("YOUR_TELEGRAM_USER_ID", "0"))


def owner_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != OWNER_ID and OWNER_ID != 0:
            await update.message.reply_text("⛔ This bot is private.")
            return
        return await func(update, context)
    return wrapper


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

    # Pass owner_id to jobs via bot_data
    app.bot_data["owner_id"] = OWNER_ID

    # Wrap handlers with owner_only guard
    app.add_handler(CommandHandler("start", owner_only(cmd_start)))
    app.add_handler(CommandHandler("briefing", owner_only(cmd_briefing)))
    app.add_handler(CommandHandler("tasks", owner_only(cmd_tasks)))
    app.add_handler(CommandHandler("done", owner_only(cmd_done)))
    app.add_handler(CommandHandler("add", owner_only(cmd_add)))
    app.add_handler(CommandHandler("schedule", owner_only(cmd_schedule)))
    app.add_handler(CommandHandler("conflicts", owner_only(cmd_conflicts)))
    app.add_handler(CommandHandler("rules", owner_only(cmd_rules)))
    app.add_handler(CommandHandler("decisions", owner_only(cmd_decisions)))
    app.add_handler(CommandHandler("memory", owner_only(cmd_memory)))
    app.add_handler(CommandHandler("calendars", owner_only(cmd_calendars)))
    app.add_handler(CommandHandler("settings", owner_only(cmd_settings)))
    app.add_handler(CommandHandler("emails", owner_only(cmd_emails)))
    app.add_handler(CommandHandler("email_detail", owner_only(cmd_email_detail)))
    app.add_handler(CommandHandler("email_prefs", owner_only(cmd_email_prefs)))
    app.add_handler(CommandHandler("connect_google", owner_only(cmd_connect_google)))
    app.add_handler(CommandHandler("connect_gmail", owner_only(cmd_connect_gmail)))
    app.add_handler(CommandHandler("connect_outlook", owner_only(cmd_connect_outlook)))
    app.add_handler(CallbackQueryHandler(handle_email_feedback, pattern=r"^email_fb:"))

    # Free text → Claude AI with memory
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, owner_only(handle_message)))

    # File uploads (documents + photos) → persisted for later summarise/attach/send
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, owner_only(handle_file)))

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

    logger.info("🚀 Bot is running with memory + multi-calendar!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
