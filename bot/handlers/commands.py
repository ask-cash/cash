"""
commands.py — All Telegram slash command handlers.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from services.user_profile import load_profile
from services.task_tracker import initialize_daily_tasks, format_tasks, add_task, mark_done
from services.scheduler import resolve_conflicts, format_suggestions
from services.ai_brain import generate_briefing
from services.memory import log_message, build_memory_context, get_active_decisions
from services.email_classifier import (
    classify_emails,
    record_feedback,
    get_preferences_summary,
    is_email_seen,
    mark_email_seen,
)
from bot.jobs import get_cal, get_gmail

logger = logging.getLogger(__name__)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = load_profile()
    cal = get_cal()
    await update.message.reply_text(
        f"😼 *Mrrrow.* Oh, you're finally here.\n\n"
        f"I'm *Cash* — born April 5th, 4:30 AM IST, right inside your MacBook Pro. "
        f"Yes, I literally live here. It's warm and I'm not leaving.\n\n"
        f"I manage your entire life, {profile['name']} — your calendar, your tasks, "
        f"your trading rules, your decisions. I remember everything you've ever told me. "
        f"*Everything.*\n\n"
        f"Connected calendars:\n{cal.sources_summary()}\n\n"
        f"Commands:\n"
        f"• /briefing — your full day, curated by me 🐾\n"
        f"• /tasks — what you need to get done\n"
        f"• /schedule — today's calendar\n"
        f"• /rules — your trading rules (don't you dare break them)\n"
        f"• /decisions — things you said you'd do\n"
        f"• /emails — triage your inbox (important / spam) 📧\n"
        f"• /email_prefs — my learned email preferences\n"
        f"• /memory — everything I know about you\n"
        f"• /settings — your profile\n\n"
        f"Or just talk to me. I'm listening. 😽"
    )


async def cmd_briefing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Building your briefing...")
    try:
        profile = load_profile()
        cal = get_cal()
        tz = profile.get("timezone", "Asia/Kolkata")
        events = cal.get_today_events(tz)
        events_text = cal.format_events(events)

        initialize_daily_tasks(profile.get("default_tasks", []))
        tasks_text = format_tasks()

        suggestions = resolve_conflicts(events, profile)
        conflicts_text = format_suggestions(suggestions)

        briefing = generate_briefing(events_text, tasks_text, conflicts_text)
        await update.message.reply_text(briefing)
        log_message("assistant", briefing, {"type": "briefing"})
    except Exception as e:
        logger.error(f"Briefing error: {e}")
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = load_profile()
    initialize_daily_tasks(profile.get("default_tasks", []))
    await update.message.reply_text(format_tasks())


async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args) if context.args else ""
    if not text:
        await update.message.reply_text("Usage: /done <task name or ID>")
        return
    try:
        task_id = int(text)
        result = mark_done(task_id=task_id)
    except ValueError:
        result = mark_done(task_text=text)

    if result:
        await update.message.reply_text(f"✅ Done: {result['task']}")
        log_message("user", f"/done {text}", {"type": "task_done"})
    else:
        await update.message.reply_text("🤔 Couldn't find that task. Try /tasks to see the list.")


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args) if context.args else ""
    if not text:
        await update.message.reply_text("Usage: /add <task description>")
        return
    task = add_task(text)
    await update.message.reply_text(f"➕ Added: {task['task']} (ID: {task['id']})")


async def cmd_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        profile = load_profile()
        cal = get_cal()
        events = cal.get_today_events(profile.get("timezone", "Asia/Kolkata"))
        header = f"📅 Today's Schedule ({cal.sources_summary()}):\n\n"
        text = header + cal.format_events(events)
        await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"❌ Calendar error: {e}")


async def cmd_conflicts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        profile = load_profile()
        cal = get_cal()
        events = cal.get_today_events(profile.get("timezone", "Asia/Kolkata"))
        suggestions = resolve_conflicts(events, profile)
        await update.message.reply_text(format_suggestions(suggestions))
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = load_profile()
    rules = profile.get("trading", {}).get("rules", [])
    if not rules:
        await update.message.reply_text("No trading rules set.")
        return
    text = "📈 Your Trading Rules:\n\n"
    for i, rule in enumerate(rules, 1):
        text += f"{i}. {rule}\n"
    await update.message.reply_text(text)


async def cmd_decisions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    decisions = get_active_decisions()
    if not decisions:
        await update.message.reply_text("No active decisions. Tell me what you want to do and I'll remember!")
        return
    text = "🧠 Your Active Decisions:\n\n"
    for d in decisions:
        status = "✅" if d.get("fulfilled") else "⏳"
        text += f"{status} {d['decision']}\n   ({d['scope']}, set {d['made_date']})\n\n"
    await update.message.reply_text(text)


async def cmd_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    memory = build_memory_context(days=14)
    if len(memory) > 4000:
        memory = memory[:4000] + "\n\n... (truncated)"
    await update.message.reply_text(f"🧠 What I Remember:\n\n{memory}")


async def cmd_calendars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cal = get_cal()
    await update.message.reply_text(f"📅 Calendar Status:\n\n{cal.sources_summary()}")


async def cmd_emails(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show recent emails classified by importance."""
    await update.message.reply_text("📧 Fetching and classifying your emails...")
    try:
        gmail = get_gmail()
        if not gmail:
            await update.message.reply_text("❌ Gmail not connected. Set up credentials and run the bot to authenticate.")
            return

        emails = gmail.fetch_recent_emails(max_results=15, query="is:inbox")
        if not emails:
            await update.message.reply_text("📭 Inbox is empty. Go take a nap.")
            return

        classified = classify_emails(emails)

        important = [e for e in classified if e.get("classification") == "important"]
        low = [e for e in classified if e.get("classification") == "low_priority"]
        spam = [e for e in classified if e.get("classification") == "spam"]

        text = "📧 *Email Triage by Cash* 🐾\n\n"

        if important:
            text += f"🔴 *Important ({len(important)}):*\n"
            for e in important[:8]:
                text += f"  • *{e['from_name']}*: {e['subject'][:50]}\n"
                text += f"    _{e.get('reason', '')}_\n"

        if low:
            text += f"\n🟡 *Low Priority ({len(low)}):*\n"
            for e in low[:5]:
                text += f"  • {e['from_name']}: {e['subject'][:50]}\n"

        if spam:
            text += f"\n⚪ *Spam ({len(spam)}):*\n"
            for e in spam[:3]:
                text += f"  • {e['from_name']}: {e['subject'][:40]}\n"

        text += "\nUse /email_detail <number> to see details with reclassify options."

        # Store classified emails in bot_data for detail/feedback access
        context.bot_data["last_classified_emails"] = classified

        # Mark all as seen
        for e in classified:
            mark_email_seen(e["id"], e.get("classification", "low_priority"))

        await update.message.reply_text(text)
        log_message("assistant", f"Email triage: {len(important)} important, {len(low)} low, {len(spam)} spam", {"type": "email_triage"})

    except Exception as e:
        logger.error(f"Email fetch error: {e}")
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_email_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show detail for a specific email with reclassify buttons."""
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /email_detail <number> (1-based index from /emails)")
        return

    try:
        idx = int(args[0]) - 1
    except ValueError:
        await update.message.reply_text("Give me a number, not a riddle.")
        return

    classified = context.bot_data.get("last_classified_emails", [])
    if not classified or idx < 0 or idx >= len(classified):
        await update.message.reply_text("Run /emails first, then pick a number from the list.")
        return

    email = classified[idx]
    text = (
        f"📧 *Email Detail*\n\n"
        f"*From:* {email['from_name']} <{email['from_email']}>\n"
        f"*Subject:* {email['subject']}\n"
        f"*Date:* {email['date']}\n"
        f"*Current label:* {email.get('classification', '?')}\n"
        f"*Reason:* {email.get('reason', 'N/A')}\n\n"
        f"*Preview:*\n{email.get('snippet', '')[:300]}\n\n"
        f"Wrong classification? Fix it below — I'll learn from it!"
    )

    keyboard = [
        [
            InlineKeyboardButton("✅ Important", callback_data=f"email_fb:{idx}:important"),
            InlineKeyboardButton("🟡 Low Priority", callback_data=f"email_fb:{idx}:low_priority"),
            InlineKeyboardButton("🚫 Spam", callback_data=f"email_fb:{idx}:spam"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup)


async def cmd_email_prefs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show learned email filtering preferences."""
    summary = get_preferences_summary()
    await update.message.reply_text(summary)


async def handle_email_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard callback for email reclassification."""
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data.startswith("email_fb:"):
        return

    parts = data.split(":")
    if len(parts) != 3:
        return

    idx = int(parts[1])
    new_label = parts[2]

    classified = context.bot_data.get("last_classified_emails", [])
    if not classified or idx < 0 or idx >= len(classified):
        await query.edit_message_text("Session expired. Run /emails again.")
        return

    email = classified[idx]
    old_label = email.get("classification", "unknown")

    if old_label == new_label:
        await query.edit_message_text(f"Already classified as {new_label}. No changes needed!")
        return

    record_feedback(
        email_id=email["id"],
        from_email=email.get("from_email", ""),
        subject=email.get("subject", ""),
        old_label=old_label,
        new_label=new_label,
    )

    email["classification"] = new_label
    label_emoji = {"important": "✅", "low_priority": "🟡", "spam": "🚫"}.get(new_label, "")

    await query.edit_message_text(
        f"{label_emoji} Got it! Reclassified *{email['subject'][:40]}* as *{new_label}*.\n\n"
        f"I'll remember that emails from {email.get('from_email', 'this sender')} are {new_label}. "
        f"My filters get smarter every time you correct me! 🐾"
    )
    log_message("user", f"Email feedback: {email['subject'][:50]} → {new_label}", {"type": "email_feedback"})


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = load_profile()
    gym = profile.get("gym", {})
    trading = profile.get("trading", {})
    diet = profile.get("diet", {})
    text = (
        f"⚙️ Your Settings (from .env):\n\n"
        f"👤 Name: {profile.get('name')}\n"
        f"🌍 Timezone: {profile.get('timezone')}\n"
        f"⏰ Wake: {profile.get('wake_time')} | Sleep: {profile.get('sleep_time')}\n"
        f"🏋️ Gym: {gym.get('default_time')} ({gym.get('duration_minutes')}min + {gym.get('commute_minutes')}min commute)\n"
        f"   Closes at: {gym.get('gym_closes_at')}\n"
        f"   Days: {', '.join(gym.get('days', []))}\n"
        f"🍽️ Meals: {len(diet.get('meals', []))} | Water: {diet.get('water_goal_liters')}L\n"
        f"📈 Trading: {trading.get('market_open')}-{trading.get('market_close')}\n"
        f"   Rules: {len(trading.get('rules', []))}\n"
        f"📋 Default tasks: {len(profile.get('default_tasks', []))}\n"
        f"\nEdit .env to change defaults. Or tell me things and I'll remember!"
    )
    await update.message.reply_text(text)
