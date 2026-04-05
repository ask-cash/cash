"""
messages.py — Natural language message handler with AI brain + memory.
"""

import logging
import datetime as dt
from telegram import Update
from telegram.ext import ContextTypes

from services.user_profile import load_profile
from services.task_tracker import initialize_daily_tasks, format_tasks, add_task, mark_done
from services.scheduler import resolve_conflicts, format_suggestions
from services.ai_brain import interpret_message
from services.memory import (
    log_message,
    store_fact,
    store_decision,
    fulfill_decision,
    log_trade,
    get_active_decisions,
    search_conversations,
)
from bot.jobs import get_cal

logger = logging.getLogger(__name__)


def process_memory_ops(ops: list[dict]):
    """Execute memory operations returned by the AI brain."""
    if not ops:
        return
    for op in ops:
        try:
            if op["op"] == "store_fact":
                store_fact(op.get("fact", ""), op.get("category", "general"))
            elif op["op"] == "store_decision":
                store_decision(op.get("decision", ""), op.get("scope", "today"))
            elif op["op"] == "fulfill_decision":
                fulfill_decision(op.get("decision_text", ""))
            elif op["op"] == "log_trade":
                log_trade({
                    "symbol": op.get("symbol", ""),
                    "action": op.get("action", ""),
                    "result": op.get("result", ""),
                    "notes": op.get("notes", ""),
                })
        except Exception as e:
            logger.error(f"Memory op error: {e}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text
    if not user_msg:
        return

    log_message("user", user_msg)

    try:
        result = interpret_message(user_msg)
        action = result.get("action", "chat")
        params = result.get("params", {})
        reply = result.get("reply", "")
        memory_ops = result.get("memory_ops", [])

        process_memory_ops(memory_ops)

        if action == "show_tasks":
            profile = load_profile()
            initialize_daily_tasks(profile.get("default_tasks", []))
            reply = format_tasks()

        elif action == "show_schedule":
            profile = load_profile()
            cal = get_cal()
            events = cal.get_today_events(profile.get("timezone", "Asia/Kolkata"))
            reply = f"📅 Today's Schedule:\n\n{cal.format_events(events)}"

        elif action == "show_tomorrow":
            profile = load_profile()
            cal = get_cal()
            events = cal.get_tomorrow_events(profile.get("timezone", "Asia/Kolkata"))
            reply = f"📅 Tomorrow's Schedule:\n\n{cal.format_events(events)}"

        elif action == "show_briefing":
            await update.message.reply_text("⏳ Building briefing...")
            from bot.handlers.commands import cmd_briefing
            await cmd_briefing(update, context)
            return

        elif action == "add_task":
            task = add_task(
                params.get("task", user_msg),
                params.get("time", ""),
                params.get("category", "general"),
            )
            reply = reply or f"➕ Added: {task['task']}"

        elif action == "mark_done":
            result_task = mark_done(task_text=params.get("task_text", ""))
            if result_task:
                reply = reply or f"✅ Done: {result_task['task']}"
            else:
                reply = reply or "🤔 Couldn't find that task."

        elif action == "check_conflicts":
            profile = load_profile()
            cal = get_cal()
            events = cal.get_today_events(profile.get("timezone", "Asia/Kolkata"))
            suggestions = resolve_conflicts(events, profile)
            reply = format_suggestions(suggestions)

        elif action == "show_trading_rules":
            profile = load_profile()
            rules = profile.get("trading", {}).get("rules", [])
            reply = "📈 Trading Rules:\n" + "\n".join(f"{i}. {r}" for i, r in enumerate(rules, 1))

        elif action == "add_trading_rule":
            rule = params.get("rule", "")
            store_decision(f"New trading rule: {rule}", scope="permanent")
            reply = reply or f"✅ Remembered new rule: {rule}"

        elif action == "create_event":
            cal = get_cal()
            today = dt.date.today()
            start_time = dt.time.fromisoformat(params.get("start_time", "09:00"))
            start = dt.datetime.combine(today, start_time)
            duration = params.get("duration_minutes", 60)
            end = start + dt.timedelta(minutes=duration)
            target_cal = params.get("calendar", "google")
            cal.create_event(params.get("title", "New Event"), start, end, calendar=target_cal)
            reply = reply or f"📅 Created: {params.get('title')} at {params.get('start_time')} on {target_cal}"

        elif action == "move_event":
            reply = reply or f"I'll note that you want to move '{params.get('event_title')}' to {params.get('new_time')}."

        elif action == "search_memory":
            query = params.get("query", "")
            results = search_conversations(query, days=30)
            if results:
                reply = f"🔍 Found {len(results)} mentions of '{query}':\n\n"
                for r in results[-5:]:
                    reply += f"[{r['date']}] {r['role']}: {r['text'][:100]}\n\n"
            else:
                reply = f"No mentions of '{query}' in the last 30 days."

        elif action == "show_decisions":
            decisions = get_active_decisions()
            if decisions:
                reply = "🧠 Active Decisions:\n\n"
                for d in decisions:
                    status = "✅" if d.get("fulfilled") else "⏳"
                    reply += f"{status} {d['decision']} ({d['scope']}, {d['made_date']})\n"
            else:
                reply = "No active decisions."

        elif action == "show_calendars":
            cal = get_cal()
            reply = f"📅 Calendar Status:\n\n{cal.sources_summary()}"

        final_reply = reply or "👍"
        await update.message.reply_text(final_reply)
        log_message("assistant", final_reply)

    except Exception as e:
        logger.error(f"Message handling error: {e}")
        await update.message.reply_text(f"Sorry, something went wrong: {e}")
