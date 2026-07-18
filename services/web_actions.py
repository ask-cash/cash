"""
web_actions.py — surface-agnostic execution of brain actions.

The Telegram handler interprets a message into an ``(action, params)`` and then
executes it against the real calendar / tasks / reminders / memory services.
This module does the same execution **without any Telegram objects**, so the web
dashboard chat runs the same actions and returns the authoritative text result.

``execute(action, params)`` runs under the caller's tenant context and returns a
string result, or ``None`` when the action isn't handled here (the caller then
falls back to the brain's conversational reply). Every handler is best-effort:
a failure returns a friendly message rather than raising.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_READ_CALENDAR = {"show_schedule", "show_tomorrow", "show_date", "check_conflicts", "show_calendars"}
_WRITE_CALENDAR = {"create_event", "delete_event"}


def _tz(profile: dict) -> ZoneInfo:
    try:
        return ZoneInfo(profile.get("timezone") or "Asia/Kolkata")
    except Exception:
        return ZoneInfo("Asia/Kolkata")


def execute(action: str, params: dict, *, surface: str = "dashboard") -> Optional[str]:
    """Execute a brain action; return its text result, or None if unhandled."""
    params = params or {}
    try:
        return _dispatch(action, params, surface=surface)
    except Exception:
        logger.exception("[web_actions] %s failed", action)
        return "😿 I hit a snag running that — try again in a moment."


def _dispatch(action: str, params: dict, *, surface: str = "dashboard") -> Optional[str]:
    from services.user_profile import load_profile
    profile = load_profile()

    # ---- tasks ----
    if action == "show_tasks":
        from services.task_tracker import initialize_daily_tasks, format_tasks
        initialize_daily_tasks(profile.get("default_tasks", []))
        return format_tasks()
    if action == "add_task":
        from services.task_tracker import add_task
        t = add_task(params.get("task", ""), params.get("time", ""), params.get("category", "general"))
        return f"➕ Added: {t['task']}"
    if action == "mark_done":
        from services.task_tracker import mark_done
        r = mark_done(task_text=params.get("task_text", ""))
        return f"✅ Done: {r['task']}" if r else "🤔 I couldn't find that task."

    # ---- calendar (read) ----
    if action in _READ_CALENDAR:
        return _calendar_read(action, params, profile)

    # ---- calendar (write) ----
    if action in _WRITE_CALENDAR:
        return _calendar_write(action, params, profile)

    # ---- reminders ----
    if action == "show_reminders":
        from services import reminders
        pend = reminders.list_pending()
        if not pend:
            return "You have no reminders set."
        lines = ["⏰ Your reminders:"]
        for r in pend:
            when = r.get("when", "")
            lines.append(f"  • {r.get('text', '')} — {when[:16].replace('T', ' ')}")
        return "\n".join(lines)
    if action in ("set_reminder", "set_reminders"):
        return _set_reminders(action, params)

    # ---- trading ----
    if action == "show_trading_rules":
        rules = (profile.get("trading", {}) or {}).get("rules", [])
        if not rules:
            return "No trading rules set yet."
        return "📈 Your trading rules:\n" + "\n".join(f"{i}. {r}" for i, r in enumerate(rules, 1))
    if action == "add_trading_rule":
        from services.user_profile import save_profile
        rule = params.get("rule", "").strip()
        if not rule:
            return "What's the rule?"
        rules = list((profile.get("trading", {}) or {}).get("rules", []))
        rules.append(rule)
        save_profile({"trading": {"rules": rules}})
        from services.memory import store_decision
        store_decision(f"New trading rule: {rule}", scope="permanent")
        return f"📈 Rule saved: {rule}"

    # ---- memory ----
    if action == "show_decisions":
        from services.memory import get_active_decisions
        ds = get_active_decisions()
        if not ds:
            return "No active decisions on file."
        return "🧠 Active decisions:\n" + "\n".join(
            f"  {'✅' if d.get('fulfilled') else '⏳'} {d['decision']} ({d['scope']})" for d in ds)
    if action == "search_memory":
        from services.memory import search_conversations
        hits = search_conversations(params.get("query", ""), days=60)[:6]
        if not hits:
            return "I couldn't find anything about that in our history."
        return "🔎 Here's what I found:\n" + "\n".join(f"  • {h.get('text', '')[:120]}" for h in hits)

    # ---- briefing ----
    if action == "show_briefing":
        return _briefing(profile, surface=surface)

    # ---- profile ----
    if action == "update_profile":
        from services.user_profile import save_profile
        save_profile(params)
        return "Got it — I've updated your profile. 🐾"

    # Not handled here — caller uses the brain's conversational reply.
    return None


def _calendar_read(action: str, params: dict, profile: dict) -> str:
    from calendars.unified import UnifiedCalendar  # built per-tenant (no shared cache)
    cal = UnifiedCalendar()
    if not (getattr(cal, "google", None) or getattr(cal, "outlook", None)):
        return ("📅 Your calendar isn't connected yet. Head to Integrations and connect "
                "Google Calendar so I can see your schedule.")
    tz = profile.get("timezone", "Asia/Kolkata")

    if action == "show_calendars":
        return f"📅 Connected calendars: {cal.sources_summary()}"
    if action == "show_schedule":
        return "📅 Today:\n" + cal.format_events(cal.get_today_events(tz))
    if action == "show_tomorrow":
        return "📅 Tomorrow:\n" + cal.format_events(cal.get_tomorrow_events(tz))
    if action == "show_date":
        d = dt.date.fromisoformat(params["date"])
        return f"📅 {d.strftime('%A %b %d')}:\n" + cal.format_events(cal.get_events_for_date(d, tz))
    if action == "check_conflicts":
        from services.scheduler import resolve_conflicts, format_suggestions
        return format_suggestions(resolve_conflicts(cal.get_today_events(tz), profile))
    return ""


def _calendar_write(action: str, params: dict, profile: dict) -> str:
    from calendars.unified import UnifiedCalendar
    cal = UnifiedCalendar()
    if not (getattr(cal, "google", None) or getattr(cal, "outlook", None)):
        return "📅 Connect Google Calendar first (Integrations) and I'll add that for you."
    tz = _tz(profile)

    if action == "create_event":
        date = dt.date.fromisoformat(params["date"])
        hh, mm = (params.get("start_time") or "09:00").split(":")
        start = dt.datetime.combine(date, dt.time(int(hh), int(mm)), tzinfo=tz)
        end = start + dt.timedelta(minutes=int(params.get("duration_minutes") or 60))
        ok = cal.create_event(params.get("title", "Event"), start, end,
                              calendar=params.get("calendar", "google"))
        return (f"✅ Created “{params.get('title', 'Event')}” on {start.strftime('%b %d at %I:%M %p')}."
                if ok else "😿 I couldn't create that event.")

    if action == "delete_event":
        ev = cal.find_event(
            title=params.get("event_title", ""),
            event_time=params.get("event_time", ""),
            date=dt.date.fromisoformat(params["date"]) if params.get("date") and params["date"][:4].isdigit() else None,
        )
        if not ev:
            return "🤔 I couldn't find that event to delete."
        ok = cal.delete_event(ev.get("id", ""), source=ev.get("source", "google"))
        return f"🗑️ Deleted “{ev.get('title', 'that event')}”." if ok else "😿 I couldn't delete it."
    return ""


def _set_reminders(action: str, params: dict) -> str:
    from services import reminders
    items = params.get("reminders") if action == "set_reminders" else [params]
    saved = []
    for it in items or []:
        text = (it.get("text") or "").strip()
        date = it.get("date")
        time = it.get("time")
        if not (text and date and time):
            continue
        try:
            when = dt.datetime.fromisoformat(f"{date}T{time}")
        except ValueError:
            continue
        reminders.add(text, when.isoformat(), chat_id=0)
        saved.append(f"{when.strftime('%b %d %I:%M %p')} — {text}")
    if not saved:
        return "I need a what, a date and a time to set a reminder."
    return "⏰ Reminder set:\n" + "\n".join(f"  • {s}" for s in saved) + \
        "\n\n(I'll deliver these on your connected chat surfaces.)"


def _briefing(profile: dict, *, surface: str = "dashboard") -> str:
    try:
        from calendars.unified import UnifiedCalendar
        from services.task_tracker import initialize_daily_tasks, format_tasks
        from services.scheduler import resolve_conflicts, format_suggestions
        from services.ai_brain import generate_briefing
        cal = UnifiedCalendar()
        tz = profile.get("timezone", "Asia/Kolkata")
        events = cal.get_today_events(tz) if (getattr(cal, "google", None) or getattr(cal, "outlook", None)) else []
        initialize_daily_tasks(profile.get("default_tasks", []))
        return generate_briefing(
            cal.format_events(events),
            format_tasks(),
            format_suggestions(resolve_conflicts(events, profile)),
            surface=surface,
        )
    except Exception:
        logger.exception("[web_actions] briefing failed")
        return "😿 I couldn't put the briefing together right now."
