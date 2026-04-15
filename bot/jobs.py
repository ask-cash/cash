"""
jobs.py — Scheduled background jobs and shared calendar singleton.
"""

import logging
import datetime as dt
from typing import Optional
from telegram.ext import ContextTypes

from calendars.unified import UnifiedCalendar
from services.user_profile import load_profile
from services.task_tracker import initialize_daily_tasks, format_tasks, get_tasks_summary
from services.scheduler import resolve_conflicts, format_suggestions
from services.ai_brain import generate_briefing
from services.memory import log_message, get_active_decisions
from services.gmail import GmailManager
from services.email_classifier import classify_emails, is_email_seen, mark_email_seen

logger = logging.getLogger(__name__)

_cal: Optional[UnifiedCalendar] = None
_gmail: Optional[GmailManager] = None


def get_cal() -> UnifiedCalendar:
    global _cal
    if _cal is None:
        _cal = UnifiedCalendar()
    return _cal


def reset_cal() -> UnifiedCalendar:
    """Force a fresh UnifiedCalendar — call after OAuth re-auth."""
    global _cal
    _cal = UnifiedCalendar()
    return _cal


def get_gmail() -> Optional[GmailManager]:
    global _gmail
    if _gmail is None:
        try:
            _gmail = GmailManager()
        except Exception as e:
            logger.warning(f"Gmail not available: {e}")
            return None
    return _gmail


def reset_gmail() -> Optional[GmailManager]:
    """Force a fresh GmailManager — call after OAuth re-auth."""
    global _gmail
    _gmail = None
    return get_gmail()


async def scheduled_morning_briefing(context: ContextTypes.DEFAULT_TYPE):
    owner_id = context.bot_data.get("owner_id", 0)
    if owner_id == 0:
        return
    try:
        profile = load_profile()
        cal = get_cal()
        events = cal.get_today_events(profile.get("timezone", "Asia/Kolkata"))
        events_text = cal.format_events(events)
        initialize_daily_tasks(profile.get("default_tasks", []))
        tasks_text = format_tasks()
        suggestions = resolve_conflicts(events, profile)
        conflicts_text = format_suggestions(suggestions)
        briefing = generate_briefing(events_text, tasks_text, conflicts_text)
        await context.bot.send_message(chat_id=owner_id, text=f"😼 *paws at your face* Wake up, Suhail. I've been awake since 4:30 AM — this is nothing for me.\n\n{briefing}")
        log_message("assistant", "Morning briefing sent", {"type": "scheduled_briefing"})
    except Exception as e:
        logger.error(f"Morning briefing error: {e}")


async def scheduled_trading_reminder(context: ContextTypes.DEFAULT_TYPE):
    owner_id = context.bot_data.get("owner_id", 0)
    if owner_id == 0:
        return
    profile = load_profile()
    rules = profile.get("trading", {}).get("rules", [])
    if rules:
        text = "😾 *sits on your keyboard*\n\nMarket opens soon. You know the rules — I wrote them on the wall with my claws so you'd remember:\n\n"
        for i, rule in enumerate(rules, 1):
            text += f"{i}. {rule}\n"

        decisions = get_active_decisions()
        trading_decisions = [d for d in decisions if "trad" in d.get("decision", "").lower()]
        if trading_decisions:
            text += "\n🧠 You also told me you wanted to:\n"
            for d in trading_decisions:
                text += f"  • {d['decision']}\n"

        text += "\nNo revenge trading. No emotions. I'm watching. 🐾"
        await context.bot.send_message(chat_id=owner_id, text=text)


async def scheduled_meeting_check(context: ContextTypes.DEFAULT_TYPE):
    owner_id = context.bot_data.get("owner_id", 0)
    if owner_id == 0:
        return
    try:
        cal = get_cal()
        if cal.google:
            now = dt.datetime.utcnow()
            past = now - dt.timedelta(minutes=35)
            events = cal.google.service.events().list(
                calendarId="primary",
                timeMin=past.isoformat() + "Z",
                timeMax=now.isoformat() + "Z",
                singleEvents=True,
            ).execute().get("items", [])

            for ev in events:
                title = ev.get("summary", "Untitled")
                attendees = ev.get("attendees", [])
                for att in attendees:
                    if att.get("self") and att.get("responseStatus") in ("needsAction",):
                        await context.bot.send_message(
                            chat_id=owner_id,
                            text=f"🐱 Hey — '{title}' just ended and you haven't confirmed your attendance. Did you actually go, or did you ghost it? Tell me so I can update my records.",
                        )
    except Exception as e:
        logger.error(f"Meeting check error: {e}")


async def scheduled_evening_summary(context: ContextTypes.DEFAULT_TYPE):
    owner_id = context.bot_data.get("owner_id", 0)
    if owner_id == 0:
        return
    profile = load_profile()
    initialize_daily_tasks(profile.get("default_tasks", []))
    summary = get_tasks_summary()
    done_ratio = f"{summary['done_count']}/{summary['total']}"
    if summary['done_count'] == summary['total'] and summary['total'] > 0:
        opening = f"😽 *purrs* {done_ratio} tasks done. You actually did it. I'm impressed. Almost proud enough to share my catnip."
    elif summary['done_count'] == 0:
        opening = f"😾 {done_ratio} tasks done. Zero. I did NOT wake up at 4:30 AM for this, Suhail."
    else:
        opening = f"😼 {done_ratio} tasks done. Decent. Could've been better. Could've been worse. I've seen both."

    text = f"🌙 End of Day — Cash's Report\n\n{opening}\n"

    if summary["pending"]:
        text += "\n⏳ Rolling these over to tomorrow (you're welcome):\n"
        for t in summary["pending"]:
            text += f"  • {t['task']}\n"

    decisions = get_active_decisions()
    unfulfilled = [d for d in decisions if not d.get("fulfilled") and d.get("scope") == "today"]
    if unfulfilled:
        text += "\n🧠 You said you'd do these today. You didn't:\n"
        for d in unfulfilled:
            text += f"  • {d['decision']}\n"

    text += "\nGet some sleep. I'll be here, judging you silently. 🐾"
    await context.bot.send_message(chat_id=owner_id, text=text)
    log_message("assistant", "Evening summary sent", {"type": "scheduled_summary"})


async def scheduled_email_check(context: ContextTypes.DEFAULT_TYPE):
    """Periodic job: check for new important emails and notify."""
    owner_id = context.bot_data.get("owner_id", 0)
    if owner_id == 0:
        return
    try:
        gmail = get_gmail()
        if not gmail:
            return

        emails = gmail.fetch_unread_emails(max_results=10)
        if not emails:
            return

        # Filter out already-seen emails
        new_emails = [e for e in emails if not is_email_seen(e["id"])]
        if not new_emails:
            return

        classified = classify_emails(new_emails)
        important = [e for e in classified if e.get("classification") == "important"]

        # Mark all checked emails as seen
        for e in classified:
            mark_email_seen(e["id"], e.get("classification", "low_priority"))

        if not important:
            return

        # Notify about important emails
        text = f"📬 *{len(important)} new important email{'s' if len(important) > 1 else ''}!*\n\n"
        for e in important[:5]:
            text += f"• *{e['from_name']}*: {e['subject'][:60]}\n"
            text += f"  _{e.get('reason', '')}_\n"

        text += "\nUse /emails for full triage. 🐾"
        await context.bot.send_message(chat_id=owner_id, text=text)
        log_message("assistant", f"Email alert: {len(important)} important", {"type": "email_alert"})

    except Exception as e:
        logger.error(f"Email check error: {e}")
