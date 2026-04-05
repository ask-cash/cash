"""
main.py — Entry point for the Personal AI Assistant Telegram bot.
"""

import os
import logging
import datetime as dt

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
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
)
from bot.handlers.messages import handle_message
from bot.jobs import (
    scheduled_morning_briefing,
    scheduled_trading_reminder,
    scheduled_meeting_check,
    scheduled_evening_summary,
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


def main():
    if not BOT_TOKEN:
        print("❌ Set TELEGRAM_BOT_TOKEN in .env")
        return

    app = Application.builder().token(BOT_TOKEN).build()

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

    # Free text → Claude AI with memory
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, owner_only(handle_message)))

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

    logger.info("🚀 Bot is running with memory + multi-calendar!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
