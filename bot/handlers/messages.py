"""
messages.py — Natural language message handler with AI brain + memory.
"""

import logging
import os
import re
import datetime as dt
from telegram import Update
from telegram.ext import ContextTypes

from services.user_profile import load_profile, today as ist_today
from services.task_tracker import initialize_daily_tasks, format_tasks, add_task, mark_done
from services.scheduler import resolve_conflicts, format_suggestions
from services.ai_brain import interpret_message, answer_about_file
from services.files import find_by_ref
from services.drive import upload_and_share, shorten_url
from services.memory import (
    log_message,
    store_fact,
    store_decision,
    fulfill_decision,
    log_trade,
    get_active_decisions,
    search_conversations,
)
from services.email_classifier import classify_emails, get_preferences_summary, mark_email_seen
from bot.jobs import get_cal, get_gmail

logger = logging.getLogger(__name__)

DAY_NAMES = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}


def _resolve_date(date_str: str) -> dt.date:
    """Resolve a date string to a concrete date. Handles YYYY-MM-DD, day names, today, tomorrow."""
    current_date = ist_today()

    if date_str in ("today", ""):
        return current_date
    if date_str == "tomorrow":
        return current_date + dt.timedelta(days=1)

    # Try YYYY-MM-DD first
    try:
        return dt.date.fromisoformat(date_str)
    except ValueError:
        pass

    # Try day name (e.g. "wednesday", "next friday")
    cleaned = date_str.replace("next ", "").strip()
    if cleaned in DAY_NAMES:
        target_weekday = DAY_NAMES[cleaned]
        current_weekday = current_date.weekday()
        days_ahead = (target_weekday - current_weekday) % 7
        if days_ahead == 0:
            days_ahead = 7
        return current_date + dt.timedelta(days=days_ahead)

    logger.warning(f"Could not resolve date '{date_str}', defaulting to today")
    return current_date


def _extract_time_from_text(text: str) -> str:
    """Extract a time reference like '9 am', '2:30 pm', '14:00' from text.

    Returns HH:MM in 24h format, or '' if nothing found.
    """
    # Match patterns like "9am", "9 am", "9:30 pm", "14:00"
    m = re.search(
        r'\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|AM|PM)\b', text
    )
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        period = m.group(3).lower()
        if period == "pm" and hour != 12:
            hour += 12
        elif period == "am" and hour == 12:
            hour = 0
        return f"{hour:02d}:{minute:02d}"

    # 24h format like "14:00"
    m = re.search(r'\b([01]?\d|2[0-3]):([0-5]\d)\b', text)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"

    return ""


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
    print(f"User message: {update}")
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
            title = params.get("title", "New Event")
            target_cal = params.get("calendar", "google")
            try:
                date_str = (params.get("date") or "today").strip().lower()
                event_date = _resolve_date(date_str)
                start_time = dt.time.fromisoformat(params.get("start_time", "09:00"))
                start = dt.datetime.combine(event_date, start_time)
                duration = params.get("duration_minutes", 60)
                end = start + dt.timedelta(minutes=duration)
                result = cal.create_event(title, start, end, calendar=target_cal)
                if result:
                    reply = reply or f"📅 Created '{title}' at {params.get('start_time')} on {event_date.strftime('%A, %b %d')} ({target_cal.capitalize()} Calendar)."
                else:
                    reply = f"😿 Failed to create '{title}' on {target_cal.capitalize()} Calendar. The calendar may not be connected."
            except Exception as e:
                logger.error("Failed to create event '%s': %s", title, e)
                reply = f"😿 Failed to create '{title}' on {target_cal.capitalize()} Calendar: {e}"

        elif action == "delete_event":
            cal = get_cal()
            event_title = params.get("event_title", "")
            event_time = params.get("event_time", "")
            date_param = params.get("date", "today")
            target_date = _resolve_date((date_param or "today").strip().lower())

            if not event_time:
                event_time = _extract_time_from_text(user_msg)
                if event_time:
                    logger.info("Extracted time '%s' from user message as fallback", event_time)

            event = cal.find_event(
                title=event_title, event_time=event_time, date=target_date
            )
            if event:
                source = event.get("_source", params.get("source", "google"))
                try:
                    success = cal.delete_event(event["id"], source=source)
                except Exception as e:
                    logger.error("Exception deleting event '%s': %s", event.get("summary"), e)
                    success = False
                if success:
                    reply = f"🗑️ Deleted '{event.get('summary')}' from {source.capitalize()} Calendar."
                else:
                    reply = f"😿 Could not delete '{event.get('summary')}' from {source.capitalize()} Calendar. The delete failed on the calendar."
            else:
                desc = f"'{event_title}'" if event_title else f"at {event_time}"
                reply = f"😿 Could not find an event matching {desc} on {target_date}. No event was deleted."

        elif action == "move_event":
            cal = get_cal()
            event_title = params.get("event_title", "")
            event_time = params.get("event_time", "")
            new_time = params.get("new_time", "")
            # If AI didn't extract event_time, try extracting from user message
            if not event_time:
                event_time = _extract_time_from_text(user_msg)
                if event_time:
                    logger.info("Extracted time '%s' from user message as fallback", event_time)
            event = cal.find_event(title=event_title, event_time=event_time)
            if event and new_time:
                source = event.get("_source", "google")
                start_raw = event.get("start", {}).get("dateTime", "")
                if start_raw:
                    try:
                        old_start = dt.datetime.fromisoformat(start_raw)
                        end_raw = event.get("end", {}).get("dateTime", "")
                        if end_raw:
                            old_end = dt.datetime.fromisoformat(end_raw)
                            duration = int((old_end - old_start).total_seconds() / 60)
                        else:
                            duration = 60
                        new_start_time = dt.time.fromisoformat(new_time)
                        new_start = dt.datetime.combine(old_start.date(), new_start_time)
                        result = cal.move_event(event["id"], new_start, duration, source=source)
                        if result:
                            reply = f"📅 Moved '{event.get('summary')}' to {new_time} on {source.capitalize()} Calendar."
                        else:
                            reply = f"😿 Could not move '{event.get('summary')}' on {source.capitalize()} Calendar. The update failed on the calendar."
                    except Exception as e:
                        logger.error("Exception moving event '%s': %s", event.get("summary"), e)
                        reply = f"😿 Could not move '{event.get('summary')}' on {source.capitalize()} Calendar: {e}"
                else:
                    reply = f"😿 Could not move '{event.get('summary')}' — the event has no start time to work with."
            elif not event:
                desc = f"'{event_title}'" if event_title else f"at {event_time}"
                reply = f"😿 Could not find an event matching {desc}. No event was moved."
            else:
                reply = f"😿 No new time specified for '{event.get('summary')}'. Could not move the event."

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

        elif action == "check_emails":
            gmail = get_gmail()
            if not gmail:
                reply = "❌ Gmail not connected yet."
            else:
                emails = gmail.fetch_recent_emails(max_results=15, query="is:inbox")
                if not emails:
                    reply = reply or "📭 Inbox is empty!"
                else:
                    classified = classify_emails(emails)
                    important = [e for e in classified if e.get("classification") == "important"]
                    low = [e for e in classified if e.get("classification") == "low_priority"]
                    spam = [e for e in classified if e.get("classification") == "spam"]
                    for e in classified:
                        mark_email_seen(e["id"], e.get("classification", "low_priority"))
                    reply = reply or (
                        f"📧 Email Triage:\n\n"
                        f"🔴 Important: {len(important)}\n"
                        f"🟡 Low Priority: {len(low)}\n"
                        f"⚪ Spam: {len(spam)}\n\n"
                    )
                    if important:
                        reply += "Top important:\n"
                        for e in important[:5]:
                            reply += f"  • {e['from_name']}: {e['subject'][:50]}\n"
                    reply += "\nUse /emails for full details with reclassify options."

        elif action == "show_email_prefs":
            reply = get_preferences_summary()

        elif action == "summarize_file":
            record = find_by_ref(params.get("file_ref", ""))
            if not record:
                reply = "😿 I don't have any uploaded file to work with — send me one first."
            else:
                await update.message.reply_text(f"📄 Reading '{record['name']}'...")
                question = params.get("question") or user_msg
                try:
                    reply = answer_about_file(record, question)
                except Exception as e:
                    logger.error("answer_about_file failed for '%s': %s", record.get("name"), e)
                    reply = f"😿 Couldn't read '{record['name']}': {e}"

        elif action == "send_file":
            record = find_by_ref(params.get("file_ref", ""))
            if not record:
                reply = "😿 I don't have any uploaded file to send — upload one first."
            else:
                path = record.get("path", "")
                if not path or not os.path.exists(path):
                    reply = f"😿 The file '{record['name']}' is missing on disk."
                else:
                    try:
                        with open(path, "rb") as f:
                            await update.message.reply_document(
                                document=f,
                                filename=record.get("name"),
                                caption=reply or f"📎 Here's '{record['name']}'",
                            )
                        log_message("assistant", f"[sent file: {record['name']}]")
                        return
                    except Exception as e:
                        logger.error("Failed to send file '%s': %s", record.get("name"), e)
                        reply = f"😿 Couldn't send '{record['name']}': {e}"

        elif action == "upload_to_drive":
            record = find_by_ref(params.get("file_ref", ""))
            if not record:
                reply = "😿 No uploaded file to put on Drive — send me one first."
            else:
                await update.message.reply_text(f"☁️ Uploading '{record['name']}' to Drive...")
                drive_file = None
                error_msg = ""
                try:
                    drive_file = upload_and_share(
                        record.get("path", ""),
                        record.get("name", "upload"),
                        record.get("mime_type", ""),
                    )
                except Exception as e:
                    logger.error("upload_to_drive failed: %s", e)
                    error_msg = str(e)

                if drive_file and drive_file.get("webViewLink"):
                    short = shorten_url(drive_file["webViewLink"])
                    link_line = (
                        f"☁️ '{drive_file.get('name', record['name'])}' is on Drive.\n"
                        f"🔗 {short}"
                    )
                    reply = f"{reply}\n\n{link_line}" if reply else link_line
                else:
                    detail = f": {error_msg}" if error_msg else ". Is Google connected?"
                    reply = f"😿 Couldn't upload '{record['name']}' to Drive{detail}"

        elif action == "attach_file_to_event":
            record = find_by_ref(params.get("file_ref", ""))
            if not record:
                reply = "😿 No uploaded file to attach — send me one first."
            else:
                cal = get_cal()
                title = params.get("title", f"Event for {record['name']}")
                target_cal = params.get("calendar", "google")
                try:
                    date_str = (params.get("date") or "today").strip().lower()
                    event_date = _resolve_date(date_str)
                    start_time = dt.time.fromisoformat(params.get("start_time", "09:00"))
                    start = dt.datetime.combine(event_date, start_time)
                    duration = params.get("duration_minutes", 60)
                    end = start + dt.timedelta(minutes=duration)

                    drive_file = None
                    if target_cal == "google":
                        await update.message.reply_text(f"☁️ Uploading '{record['name']}' to Drive...")
                        drive_file = upload_and_share(
                            record.get("path", ""),
                            record.get("name", "upload"),
                            record.get("mime_type", ""),
                        )

                    short_link = ""
                    if drive_file and drive_file.get("webViewLink"):
                        short_link = shorten_url(drive_file["webViewLink"])

                    description_lines = [f"📎 {record['name']}"]
                    if short_link:
                        description_lines.append(f"Drive link: {short_link}")
                    else:
                        description_lines.append(f"Local path: {record.get('path', '')}")
                    if record.get("caption"):
                        description_lines.append(f"Caption: {record['caption']}")
                    description = "\n".join(description_lines)

                    attachments = None
                    if drive_file and drive_file.get("webViewLink"):
                        attachments = [{
                            "fileUrl": drive_file["webViewLink"],
                            "title": drive_file.get("name", record["name"]),
                            "mimeType": drive_file.get("mimeType") or record.get("mime_type", ""),
                        }]

                    result = cal.create_event(
                        title, start, end,
                        calendar=target_cal,
                        description=description,
                        attachments=attachments,
                    )
                    if result:
                        link_line = f"\n🔗 {short_link}" if short_link else ""
                        confirm = (
                            f"📅 Created '{title}' at {params.get('start_time', '09:00')} on "
                            f"{event_date.strftime('%A, %b %d')} ({target_cal.capitalize()} Calendar) "
                            f"with '{record['name']}' attached.{link_line}"
                        )
                        reply = f"{reply}\n\n{confirm}" if reply else confirm
                    else:
                        reply = f"😿 Couldn't create the event on {target_cal.capitalize()} Calendar."
                except Exception as e:
                    logger.error("attach_file_to_event failed: %s", e)
                    reply = f"😿 Couldn't attach '{record['name']}' to the event: {e}"

        final_reply = reply or "👍"
        await update.message.reply_text(final_reply)
        log_message("assistant", final_reply)

    except Exception as e:
        logger.error(f"Message handling error: {e}")
        await update.message.reply_text(f"Sorry, something went wrong: {e}")
