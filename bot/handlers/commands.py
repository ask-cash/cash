"""
commands.py — All Telegram slash command handlers.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from services.user_profile import load_profile
from services.task_tracker import initialize_daily_tasks, format_tasks, add_task, mark_done
from services.scheduler import resolve_conflicts, format_suggestions
from services.ai_brain import generate_briefing
from services.memory import log_message, build_memory_context, get_active_decisions
from bot.jobs import get_cal

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
