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


def reset_cal() -> None:
    """Drop the cached UnifiedCalendar so it's rebuilt lazily — call after OAuth
    re-auth. We must NOT rebuild eagerly here: reset_cal is invoked from the
    OAuth success callback, which runs without a tenant in context. Building
    UnifiedCalendar there would fail to load Google creds and cache a calendar
    with google=None. Clearing the cache lets the next get_cal() rebuild under
    the request handler's tenant context (mirrors reset_gmail)."""
    global _cal
    _cal = None


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
        await context.bot.send_message(chat_id=owner_id, text=f"☀️ Good morning, {profile.get('name', 'there')}. Here's your briefing for the day.\n\n{briefing}")
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
        text = "📈 Market opens soon. A quick reminder of the rules you set:\n\n"
        for i, rule in enumerate(rules, 1):
            text += f"{i}. {rule}\n"

        decisions = get_active_decisions()
        trading_decisions = [d for d in decisions if "trad" in d.get("decision", "").lower()]
        if trading_decisions:
            text += "\n🧠 You also told me you wanted to:\n"
            for d in trading_decisions:
                text += f"  • {d['decision']}\n"

        text += "\nNo revenge trading. Stay disciplined and stick to your rules."
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
                            text=f"'{title}' just ended and your attendance is still unconfirmed. Did you attend? Let me know so I can update your records.",
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
        opening = f"{done_ratio} tasks done — a full sweep. Excellent work today."
    elif summary['done_count'] == 0:
        opening = f"{done_ratio} tasks done. Nothing closed out today — let's reset and get back on track tomorrow."
    else:
        opening = f"{done_ratio} tasks done. Solid progress, with a bit more to push on tomorrow."

    text = f"🌙 End of Day — Cash's Report\n\n{opening}\n"

    if summary["pending"]:
        text += "\n⏳ Rolling these over to tomorrow:\n"
        for t in summary["pending"]:
            text += f"  • {t['task']}\n"

    decisions = get_active_decisions()
    unfulfilled = [d for d in decisions if not d.get("fulfilled") and d.get("scope") == "today"]
    if unfulfilled:
        text += "\n🧠 Still outstanding from today's commitments:\n"
        for d in unfulfilled:
            text += f"  • {d['decision']}\n"

    text += "\nGet some rest — I'll have everything ready for tomorrow."
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

        text += "\nUse /emails for full triage."
        await context.bot.send_message(chat_id=owner_id, text=text)
        log_message("assistant", f"Email alert: {len(important)} important", {"type": "email_alert"})

    except Exception as e:
        logger.error(f"Email check error: {e}")


# ---------------------------------------------------------------------------
# Proactivity (Feature 3) — heartbeat + follow-up sweep
# ---------------------------------------------------------------------------

async def scheduled_heartbeat(context: ContextTypes.DEFAULT_TYPE):
    """Hourly pulse: let Cash decide whether to nudge, and deliver if she does.

    The decision (and any LLM call) happens in services.heartbeat, off the event
    loop. Boot-safe: this only runs when the JobQueue fires it, never at import.
    """
    owner_id = context.bot_data.get("owner_id", 0)
    if owner_id == 0:
        return
    import asyncio
    from services import heartbeat
    try:
        result = await asyncio.to_thread(heartbeat.run_heartbeat)
        if result.get("spoke") and result.get("message"):
            await context.bot.send_message(chat_id=owner_id, text=result["message"])
            log_message("assistant", result["message"], {"type": "heartbeat"})
    except Exception:
        logger.exception("[jobs] heartbeat failed")


async def scheduled_followup_sweep(context: ContextTypes.DEFAULT_TYPE):
    """Surface overdue, unresolved follow-ups Cash is chasing."""
    owner_id = context.bot_data.get("owner_id", 0)
    if owner_id == 0:
        return
    from services import followups
    try:
        due = followups.sweep()
        for f in due:
            await context.bot.send_message(
                chat_id=owner_id,
                text=f"😼 Still waiting on this: {f['awaiting']} (re: {f['what']})",
            )
            followups.snooze(f["id"])  # re-surface later, don't spam every sweep
    except Exception:
        logger.exception("[jobs] follow-up sweep failed")


# ---------------------------------------------------------------------------
# Step 7 — directive lifecycle + per-person summary maintenance
# ---------------------------------------------------------------------------

async def scheduled_directive_expiry(context: ContextTypes.DEFAULT_TYPE):
    """Daily: revoke any directives whose expires_at has passed.

    Idempotent. Logs the count revoked. Cheap (single SQL UPDATE), safe to
    run more often than once a day if needed.
    """
    import asyncio
    from services.directives import store as directives_store
    try:
        count = await asyncio.to_thread(directives_store.expire_due)
        if count:
            logger.info("[jobs] expired %d directive(s)", count)
    except Exception:
        logger.exception("[jobs] directive expiry failed")


async def scheduled_summary_rollup(context: ContextTypes.DEFAULT_TYPE):
    """Daily: rebuild stale per-person summaries.

    Only people whose conversation count has grown by ≥ REBUILD_THRESHOLD_MESSAGES
    since their last summary are touched — the others are skipped, so this
    stays cheap as the people table grows.
    """
    import asyncio
    from services.identity import summaries
    try:
        rebuilt = await asyncio.to_thread(summaries.rebuild_stale)
        logger.info("[jobs] summary rollup: rebuilt %d people", rebuilt)
    except Exception:
        logger.exception("[jobs] summary rollup failed")
