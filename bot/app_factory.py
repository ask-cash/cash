"""
app_factory.py — Shared python-telegram-bot Application builder.

Both the legacy single-tenant entrypoint (main.py, long-polling) and the
multi-tenant worker (which feeds updates from the queue) need the exact same
set of handlers. Defining them once here keeps the two paths from drifting.

Scheduling (briefings/email sweeps) is intentionally NOT registered here — in
the cloud-native deployment those run as Kubernetes CronJobs (see app/cron.py),
while main.py adds its own job_queue for local single-process use.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from bot.handlers.commands import (
    cmd_start, cmd_briefing, cmd_tasks, cmd_done, cmd_add, cmd_schedule,
    cmd_conflicts, cmd_rules, cmd_decisions, cmd_memory, cmd_calendars,
    cmd_settings, cmd_emails, cmd_email_detail, cmd_email_prefs,
    cmd_connect_google, cmd_connect_gmail, cmd_connect_outlook,
    handle_email_feedback,
)
from bot.handlers.directives_commands import (
    cmd_directives, cmd_forget, cmd_revoke, cmd_unignore,
)
from bot.handlers.messages import handle_text_message
from bot.handlers.files import handle_file


def make_owner_guard(owner_id: int):
    """Wrap a handler so only the tenant owner (or anyone, if owner_id==0) is served."""
    def owner_only(func):
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if owner_id != 0 and update.effective_user and update.effective_user.id != owner_id:
                if update.message:
                    await update.message.reply_text("⛔ This bot is private.")
                return
            return await func(update, context)
        return wrapper
    return owner_only


def register_handlers(app: Application, owner_id: int = 0) -> None:
    """Attach every command/message/file handler to an Application."""
    guard = make_owner_guard(owner_id)
    app.bot_data["owner_id"] = owner_id

    app.add_handler(CommandHandler("start", guard(cmd_start)))
    app.add_handler(CommandHandler("briefing", guard(cmd_briefing)))
    app.add_handler(CommandHandler("tasks", guard(cmd_tasks)))
    app.add_handler(CommandHandler("done", guard(cmd_done)))
    app.add_handler(CommandHandler("add", guard(cmd_add)))
    app.add_handler(CommandHandler("schedule", guard(cmd_schedule)))
    app.add_handler(CommandHandler("conflicts", guard(cmd_conflicts)))
    app.add_handler(CommandHandler("rules", guard(cmd_rules)))
    app.add_handler(CommandHandler("decisions", guard(cmd_decisions)))
    app.add_handler(CommandHandler("memory", guard(cmd_memory)))
    app.add_handler(CommandHandler("calendars", guard(cmd_calendars)))
    app.add_handler(CommandHandler("settings", guard(cmd_settings)))
    app.add_handler(CommandHandler("emails", guard(cmd_emails)))
    app.add_handler(CommandHandler("email_detail", guard(cmd_email_detail)))
    app.add_handler(CommandHandler("email_prefs", guard(cmd_email_prefs)))
    app.add_handler(CommandHandler("connect_google", guard(cmd_connect_google)))
    app.add_handler(CommandHandler("connect_gmail", guard(cmd_connect_gmail)))
    app.add_handler(CommandHandler("connect_outlook", guard(cmd_connect_outlook)))
    app.add_handler(CallbackQueryHandler(handle_email_feedback, pattern=r"^email_fb:"))

    app.add_handler(CommandHandler("directives", guard(cmd_directives)))
    app.add_handler(CommandHandler("unignore", guard(cmd_unignore)))
    app.add_handler(CommandHandler("forget", guard(cmd_forget)))
    app.add_handler(CommandHandler("revoke", guard(cmd_revoke)))

    # NOT owner-guarded: handle_text_message authenticates internally so the
    # owner gets the private assistant while new users enter onboarding.
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, guard(handle_file)))


def build_application(token: str, owner_id: int = 0) -> Application:
    """Build a fully wired Application (no polling, no scheduling)."""
    app = Application.builder().token(token).build()
    register_handlers(app, owner_id=owner_id)
    return app
