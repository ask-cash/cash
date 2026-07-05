"""
messages.py — Natural language message handler with AI brain + memory.
"""

import asyncio
import contextlib
import logging
import os
import re
import time
import uuid
import datetime as dt
from types import SimpleNamespace
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from services.onboarding import assistant as onboarding_assistant
from services.onboarding import profiles as onboarding_profiles
from services.onboarding import runtime as onboarding_runtime

from services.user_profile import load_profile, save_profile, today as ist_today, now as ist_now, get_tz
from services.task_tracker import initialize_daily_tasks, format_tasks, add_task, mark_done
from services.scheduler import resolve_conflicts, format_suggestions
from services.ai_brain import interpret_message
from services.directives import parser as directives_parser
from services.directives import store as directives_store
from services.identity import people as identity_people
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
from services.files import find_by_ref, local_path_for, set_drive_link
from services.drive import upload_and_share, shorten_url
from services.ai_brain import answer_about_file
from bot.jobs import get_cal, get_gmail
from services import reminders, queue
from services.tenancy import tenant_context, current_tenant_id
from services.config import settings

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


async def _fire_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    """JobQueue callback: deliver a reminder, then clear it from the store."""
    data = context.job.data or {}
    try:
        await context.bot.send_message(
            chat_id=data["chat_id"], text=f"⏰ Reminder: {data.get('text', '')}"
        )
    except Exception:
        logger.exception("Failed to deliver reminder %s", data.get("id"))
    # Clear it under its own tenant context (the JobQueue callback does not
    # inherit the poller's tenant contextvar).
    try:
        with tenant_context(data.get("tenant_id") or settings.default_tenant_id):
            reminders.remove(data.get("id"))
    except Exception:
        logger.exception("Failed to clear reminder %s", data.get("id"))


def schedule_reminder_job(job_queue, rec: dict) -> None:
    """Schedule a persisted reminder on the JobQueue. Idempotent by job name."""
    when = dt.datetime.fromisoformat(rec["when"])
    name = f"reminder:{rec['id']}"
    for job in job_queue.get_jobs_by_name(name):
        job.schedule_removal()
    job_queue.run_once(_fire_reminder, when=when, data=rec, name=name)


def _schedule_one_reminder(context, chat_id: int, text: str, date_str: str, time_str: str):
    """Persist + schedule a single reminder. Returns (ok, line) for the reply.

    Shared by set_reminder (one) and set_reminders (many) so both behave the same.
    """
    text = (text or "your reminder").strip()
    when_dt = dt.datetime.combine(
        _resolve_date((date_str or "today").strip().lower()),
        dt.time.fromisoformat(time_str or "09:00"),
        tzinfo=get_tz(),
    )
    if when_dt <= ist_now():
        return False, f"{when_dt.strftime('%b %d at %I:%M %p')} is already past — pick a future time."
    rec = reminders.add(text, when_dt.isoformat(), chat_id)
    schedule_reminder_job(context.job_queue, rec)
    return True, f"{when_dt.strftime('%I:%M %p on %b %d')} — \"{text}\""


_CONNECT_CAL_MSG = (
    "📅 Your calendar isn't connected yet, so I can't see any events.\n"
    "Send /connect_google to link your Google Calendar and I'll start tracking your schedule."
)


def _calendar_connected(cal) -> bool:
    """True if any calendar backend (Google/Outlook) is actually connected."""
    return bool(getattr(cal, "google", None) or getattr(cal, "outlook", None))


# Short-lived cache so back-to-back messages don't each hit the calendar API.
_CAL_CTX_CACHE: dict = {}
_CAL_CTX_TTL = 60.0


def _calendar_context() -> str:
    """Today's + tomorrow's REAL events, for grounding the brain's time math
    (e.g. "remind me an hour before my dentist appointment"). Cached ~60s."""
    cal = get_cal()
    if not _calendar_connected(cal):
        return "Calendar not connected."
    tid = current_tenant_id()
    nowt = time.monotonic()
    hit = _CAL_CTX_CACHE.get(tid)
    if hit and nowt - hit[0] < _CAL_CTX_TTL:
        return hit[1]
    tz = load_profile().get("timezone", "Asia/Kolkata")
    try:
        today = cal.get_today_events(tz)
        tomorrow = cal.get_tomorrow_events(tz)
        text = (
            "TODAY:\n" + (cal.format_events(today) if today else "(no events)") +
            "\nTOMORROW:\n" + (cal.format_events(tomorrow) if tomorrow else "(no events)")
        )
    except Exception:
        logger.exception("calendar context fetch failed")
        text = "Calendar unavailable right now."
    _CAL_CTX_CACHE[tid] = (nowt, text)
    return text


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


async def _resolve_telegram_author(update: Update) -> "str | None":
    """Best-effort identity resolve for Telegram authors. Returns person_id or None."""
    try:
        u = update.effective_user
        if u is None:
            return None
        return await asyncio.to_thread(
            identity_people.resolve,
            platform="telegram",
            platform_user_id=str(u.id),
            display_name=u.full_name,
            handle=u.username,
        )
    except Exception:
        logger.exception("[identity] resolve failed for telegram update")
        return None


async def _try_handle_as_directive(update: Update, user_msg: str) -> bool:
    """Parse and act on instruction-shaped messages from Suhail.

    Returns True if the message was handled as a directive (caller should NOT
    fall through to ai_brain). Returns False to let normal chat dispatch run.

    Authority: this helper is only called from handle_message, which is wrapped
    by owner_only — so we can trust the sender is Suhail.
    """
    if not directives_parser.looks_like_instruction(user_msg):
        return False

    try:
        proposal = await asyncio.to_thread(directives_parser.parse, user_msg)
    except Exception:
        logger.exception("[directives] parser raised for: %r", user_msg[:120])
        return False
    if proposal is None:
        return False

    # Resolve target_hint → person_id (if any).
    target_person_id = None
    target_name = "(scope-only)"
    if proposal.target_hint:
        platform_filter = proposal.scope_platform if proposal.scope_platform != "*" else None
        candidates = await asyncio.to_thread(
            identity_people.find_by_hint, proposal.target_hint, platform=platform_filter,
        )
        if not candidates:
            await update.message.reply_text(
                f"I don't know anyone called '{proposal.target_hint}' yet — "
                f"they need to interact with me at least once before I can "
                f"{proposal.action} them. Try again after they've shown up."
            )
            return True
        if len(candidates) > 1:
            lines = "\n".join(
                f"  • {p.canonical_name}  ({p.person_id})"
                for p in candidates[:5]
            )
            await update.message.reply_text(
                f"Multiple people match '{proposal.target_hint}':\n{lines}\n\n"
                f"Try again with the exact handle or paste the person_id."
            )
            return True
        target_person_id = candidates[0].person_id
        target_name = candidates[0].canonical_name or proposal.target_hint

    # `unignore` is a runtime-only pseudo-action: revoke active ignore directives.
    if proposal.action == "unignore":
        if not target_person_id:
            await update.message.reply_text(
                "Need a target to unignore. Try 'unignore @alice'."
            )
            return True
        active = await asyncio.to_thread(
            directives_store.list_active_for_person, target_person_id,
        )
        revoked = 0
        for d in active:
            if d.action == "ignore":
                if directives_store.revoke(d.directive_id):
                    revoked += 1
        if revoked:
            await update.message.reply_text(
                f"Revoked {revoked} ignore directive(s) for {target_name}. "
                f"I'll respond to them again."
            )
        else:
            await update.message.reply_text(
                f"No active ignore directives found for {target_name} — "
                f"nothing to revoke."
            )
        return True

    # Create the new directive.
    try:
        directive_id = await asyncio.to_thread(
            directives_store.create,
            issued_by="suhail",
            action=proposal.action,
            target_person_id=target_person_id,
            scope_platform=proposal.scope_platform,
            scope_workspace=proposal.scope_workspace,
            scope_channel=proposal.scope_channel,
            payload=proposal.payload,
            expires_at=proposal.expires_at,
            source_text=proposal.source_text or user_msg,
        )
    except Exception:
        logger.exception("[directives] create failed for proposal=%r", proposal)
        await update.message.reply_text(
            "😿 Something went wrong storing that directive. Check the logs."
        )
        return True

    expires_phrase = ""
    if proposal.expires_at:
        # Render local for readability (parser returns ISO UTC).
        try:
            expires_dt = dt.datetime.fromisoformat(proposal.expires_at)
            expires_phrase = f" until {expires_dt.strftime('%Y-%m-%d %H:%M %Z') or expires_dt.isoformat()}"
        except ValueError:
            expires_phrase = f" until {proposal.expires_at}"

    scope_phrase = ""
    if proposal.scope_platform != "*":
        scope_phrase += f" on {proposal.scope_platform}"
    if proposal.scope_channel != "*":
        scope_phrase += f" in #{proposal.scope_channel}"

    await update.message.reply_text(
        f"Got it — {proposal.action} for {target_name}{scope_phrase}{expires_phrase}.\n"
        f"Directive {directive_id}."
    )
    logger.info(
        "[directives] issued via Telegram: %s action=%s target=%s",
        directive_id, proposal.action, target_person_id,
    )
    return True


@contextlib.asynccontextmanager
async def _keep_typing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show Telegram's 'typing…' indicator until the wrapped block exits.

    Telegram auto-clears a chat action after ~5s, so a single send would vanish
    while Cash is still thinking. This re-sends every 4s in the background and
    cancels cleanly on exit (including early returns / exceptions).

    Exposes a stopper via ``context.chat_data["_typing_stop"]`` so the reply
    reveal (`_reply_typing`) can end the indicator the moment it starts typing
    the answer out — otherwise the chat action would flicker under the message.
    """
    chat = update.effective_chat
    chat_id = chat.id if chat else None
    stop = asyncio.Event()
    if getattr(context, "chat_data", None) is not None:
        context.chat_data["_typing_stop"] = stop.set

    async def _loop():
        while chat_id is not None and not stop.is_set():
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            except Exception:  # never let the indicator break message handling
                pass
            try:  # wake early if stopped, else re-send after 4s
                await asyncio.wait_for(stop.wait(), timeout=4)
            except asyncio.TimeoutError:
                pass

    task = asyncio.create_task(_loop())
    try:
        yield
    finally:
        stop.set()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        if getattr(context, "chat_data", None) is not None:
            context.chat_data.pop("_typing_stop", None)


async def _reply_typing(msg, text: str, context=None, *, interval: float = 0.32):
    """Send `text` with a typewriter reveal: post a first chunk, then edit the
    message to grow it in word groups so it looks like Cash is typing it out.

    Smoothness comes from two things: (1) few round-trips — the number of edit
    frames scales with length but is capped, since each edit is a network call;
    (2) an EVEN cadence — we subtract the time each edit actually took from the
    target ``interval`` before sleeping, so variable Telegram latency doesn't
    make the reveal stutter.

    Stops the 'typing…' chat action first (so it doesn't flicker under the
    message), and falls back to a plain send on any Telegram error — e.g. an
    edit rate-limit (RetryAfter) — so a reply is never lost to the effect.
    """
    text = text or "👍"

    # End the thinking indicator before we start revealing the answer.
    if getattr(context, "chat_data", None):
        stopper = context.chat_data.get("_typing_stop")
        if stopper:
            stopper()

    words = text.split()
    # Not worth the effect for very short replies or very long ones (many edits).
    if len(words) <= 4 or len(text) > 3500:
        return await msg.reply_text(text)

    # ~4 words per frame, but never fewer than 3 or more than 6 edits — keeps it
    # snappy and well under Telegram's per-chat edit rate limit.
    steps = max(3, min(6, len(words) // 4))
    bounds = sorted({max(1, round(len(words) * (i + 1) / steps)) for i in range(steps)})
    sent = None
    for i, b in enumerate(bounds):
        last = i == len(bounds) - 1
        partial = " ".join(words[:b]) + ("" if last else " ▍")  # ▍ = typing cursor
        t0 = time.monotonic()
        try:
            if sent is None:
                sent = await msg.reply_text(partial)
            else:
                await sent.edit_text(partial)
        except Exception:  # rate-limited / edit failed — show the full text and bail
            if sent is None:
                return await msg.reply_text(text)
            with contextlib.suppress(Exception):
                await sent.edit_text(text)
            return sent
        if not last:
            # Even cadence regardless of how long the round-trip took.
            await asyncio.sleep(max(0.05, interval - (time.monotonic() - t0)))
    return sent


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Top-level text dispatcher: owner -> private assistant, others -> onboarding.

    Replaces the old owner-only gate on the message handler so Cash can serve
    new customers. The owner still gets the full private assistant
    (handle_message); everyone else is recognised, onboarded if new, or given a
    scoped customer assistant if already active. Owner data is never exposed to
    non-owners (active customers go through services.onboarding.assistant).
    """
    msg = update.message
    if msg is None or not msg.text:
        return

    # Show "typing…" for the whole think — covers the owner brain (handle_message)
    # and the onboarding/customer paths, all of which make slow Claude calls.
    async with _keep_typing(update, context):
        owner_id = int(context.bot_data.get("owner_id", 0) or 0)
        uid = update.effective_user.id if update.effective_user else 0
        # owner_id == 0 means "no owner configured" -> legacy single-user dev mode,
        # treat the sender as the owner (onboarding effectively off).
        is_owner = owner_id == 0 or uid == owner_id

        if is_owner:
            await handle_message(update, context)
            return

        # Non-owner path: onboarding / customer assistant.
        person_id = await _resolve_telegram_author(update)
        chat = update.effective_chat
        is_direct = getattr(chat, "type", "private") == "private"

        log_message(
            "user", msg.text,
            metadata={"surface": "telegram", "person_id": person_id} if person_id else None,
        )

        ev = SimpleNamespace(text=msg.text, is_owner=False, is_direct=is_direct)
        rr = await asyncio.to_thread(onboarding_runtime.route, ev, person_id)
        if rr.handled:
            await msg.reply_text(rr.reply)
            log_message("assistant", rr.reply,
                        metadata={"surface": "telegram", "person_id": person_id, "outcome": "onboarding"} if person_id else None)
            return

        # Active customer -> scoped assistant (never the owner's private brain).
        profile = await asyncio.to_thread(onboarding_profiles.get_profile, person_id)
        if profile is None:
            await msg.reply_text("One sec — let me get you set up.")
            return
        reply = await asyncio.to_thread(onboarding_assistant.customer_reply, profile, person_id, msg.text)
        await msg.reply_text(reply)
        log_message("assistant", reply,
                    metadata={"surface": "telegram", "person_id": person_id, "outcome": "customer-assistant"} if person_id else None)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text
    print(f"User message: {update}")
    if not user_msg:
        return

    person_id = await _resolve_telegram_author(update)

    log_message(
        "user", user_msg,
        metadata={"surface": "telegram", "person_id": person_id} if person_id else None,
    )

    # Step 5: try to interpret as a structured directive before falling through to chat.
    if await _try_handle_as_directive(update, user_msg):
        log_message(
            "assistant", "[handled as directive]",
            metadata={"surface": "telegram", "person_id": person_id, "outcome": "directive"} if person_id else None,
        )
        return

    try:
        # Run the blocking calendar fetch + Claude call in a worker thread so the
        # event loop stays free to emit the "typing…" indicator (and re-send it).
        # Doing this inline froze the loop, so typing only appeared once the reply
        # was already ready. to_thread copies contextvars, so tenant scoping holds.
        result = await asyncio.to_thread(
            lambda: interpret_message(user_msg, calendar_context=_calendar_context())
        )
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
            cal = get_cal()
            if not _calendar_connected(cal):
                reply = _CONNECT_CAL_MSG
            else:
                profile = load_profile()
                events = cal.get_today_events(profile.get("timezone", "Asia/Kolkata"))
                reply = f"📅 Today's Schedule:\n\n{cal.format_events(events)}"

        elif action == "show_tomorrow":
            cal = get_cal()
            if not _calendar_connected(cal):
                reply = _CONNECT_CAL_MSG
            else:
                profile = load_profile()
                events = cal.get_tomorrow_events(profile.get("timezone", "Asia/Kolkata"))
                reply = f"📅 Tomorrow's Schedule:\n\n{cal.format_events(events)}"

        elif action == "show_date":
            cal = get_cal()
            if not _calendar_connected(cal):
                reply = _CONNECT_CAL_MSG
            else:
                date_param = (params.get("date", "") or "").strip().lower()
                target_date = _resolve_date(date_param) if date_param else ist_today()
                events = cal.get_events_for_date(target_date)
                label = target_date.strftime("%A, %b %d")
                reply = f"📅 Schedule for {label}:\n\n{cal.format_events(events)}"

        elif action == "show_briefing":
            if not _calendar_connected(get_cal()):
                reply = _CONNECT_CAL_MSG
            else:
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
            cal = get_cal()
            if not _calendar_connected(cal):
                reply = _CONNECT_CAL_MSG
            else:
                profile = load_profile()
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
                # The actual calendar result is authoritative — NOT the LLM's
                # pre-written `reply`, which is generated before the action runs
                # and would otherwise claim success even when nothing was created.
                if result:
                    reply = f"📅 Created '{title}' at {params.get('start_time')} on {event_date.strftime('%A, %b %d')} ({target_cal.capitalize()} Calendar)."
                else:
                    reply = (
                        f"😿 I couldn't create '{title}' — your {target_cal.capitalize()} "
                        "Calendar isn't connected yet. Send /connect_google to link it, "
                        "then I'll add it for you."
                    )
            except Exception as e:
                logger.error("Failed to create event '%s': %s", title, e)
                reply = (
                    f"😿 I couldn't create '{title}' on {target_cal.capitalize()} "
                    f"Calendar — {e}"
                )

        elif action == "create_recurring_events":
            cal = get_cal()
            target_cal = params.get("calendar", "google")
            template = (params.get("title_template") or params.get("title") or "Event").strip()
            try:
                first_date = _resolve_date((params.get("start_date") or params.get("date") or "today").strip().lower())
                start_time = dt.time.fromisoformat(params.get("start_time", "09:00"))
                duration = int(params.get("duration_minutes", 60))
                interval = max(1, int(params.get("interval_days", 7)))
                count = max(1, min(int(params.get("count", 1)), 60))  # cap to avoid runaway batches

                created: list[tuple[str, dt.date]] = []
                failed: list[tuple[str, dt.date, str]] = []
                for i in range(count):
                    event_date = first_date + dt.timedelta(days=interval * i)
                    title = template.format(n=i + 1) if "{n}" in template else template
                    start = dt.datetime.combine(event_date, start_time)
                    end = start + dt.timedelta(minutes=duration)
                    try:
                        result = cal.create_event(title, start, end, calendar=target_cal)
                        if result:
                            created.append((title, event_date))
                        else:
                            failed.append((title, event_date, "calendar not connected"))
                    except Exception as e:
                        logger.error("Failed to create recurring event '%s': %s", title, e)
                        failed.append((title, event_date, str(e)))

                # The action result is authoritative — never the LLM's pre-written reply.
                lines = [
                    f"📅 Created {len(created)} of {count} events on "
                    f"{target_cal.capitalize()} Calendar:"
                ]
                lines += [f"✅ {t} — {d.strftime('%a, %b %d, %Y')}" for t, d in created]
                if failed:
                    lines.append(f"\n⚠️ {len(failed)} couldn't be created:")
                    lines += [f"❌ {t} — {d.strftime('%b %d')}: {err}" for t, d, err in failed]
                reply = "\n".join(lines)
            except Exception as e:
                logger.error("create_recurring_events failed: %s", e)
                reply = f"😿 I couldn't set up that recurring series — {e}"

        elif action == "set_reminder":
            try:
                ok, line = _schedule_one_reminder(
                    context, update.effective_chat.id,
                    params.get("text", ""), params.get("date", "today"), params.get("time", "09:00"),
                )
                reply = f"⏰ Done — I'll ping you at {line}" if ok else f"⚠️ {line}"
            except Exception as e:
                logger.error("set_reminder failed: %s", e)
                reply = f"😿 I couldn't set that reminder — {e}"

        elif action == "set_reminders":
            items = params.get("reminders") or []
            if not items:
                reply = "What should I remind you about?"
            else:
                ok_lines, fail_lines = [], []
                for it in items:
                    try:
                        ok, line = _schedule_one_reminder(
                            context, update.effective_chat.id,
                            it.get("text", ""), it.get("date", "today"), it.get("time", "09:00"),
                        )
                        (ok_lines if ok else fail_lines).append(line)
                    except Exception as e:
                        logger.error("set_reminders item failed: %s", e)
                        fail_lines.append(f"\"{it.get('text', '')}\" — {e}")
                parts = []
                if ok_lines:
                    parts.append("⏰ Done — I'll ping you:\n" + "\n".join(f"• {l}" for l in ok_lines))
                if fail_lines:
                    parts.append("⚠️ Skipped:\n" + "\n".join(f"• {l}" for l in fail_lines))
                reply = "\n\n".join(parts)

        elif action == "show_reminders":
            pending = reminders.list_pending()
            if not pending:
                reply = "You have no reminders set."
            else:
                lines = ["⏰ Your reminders:"]
                for r in pending:
                    try:
                        when_str = dt.datetime.fromisoformat(r["when"]).strftime("%b %d, %I:%M %p")
                    except Exception:
                        when_str = r.get("when", "?")
                    lines.append(f"• {when_str} — {r.get('text', '')}")
                reply = "\n".join(lines)

        elif action == "update_profile":
            allowed = {"name", "timezone", "wake_time", "sleep_time", "gym", "diet", "trading", "default_tasks"}
            clean = {k: v for k, v in (params or {}).items() if k in allowed and v not in (None, "", [], {})}
            if not clean:
                reply = reply or "Tell me a bit about your routine and I'll save it."
            else:
                try:
                    save_profile(clean)
                    reply = reply or f"✅ Saved: {', '.join(sorted(clean))}. Anything else you'd like me to remember?"
                except Exception as e:
                    logger.error("update_profile failed: %s", e)
                    reply = "😿 I couldn't save that just now — try again in a moment."

        elif action == "send_platform_message":
            target_platform = (params.get("platform") or "").strip().lower()
            text = (params.get("text") or "").strip()
            if not text:
                reply = "What should I send?"
            elif target_platform != "discord":
                reply = f"I can only send to Discord right now — not {target_platform or 'that platform'}."
            else:
                # Target the sender's OWN linked Discord identity — only if they've
                # actually connected it. No owner-secret shortcut, so we never claim
                # to send to a Discord we don't have.
                person_id = await _resolve_telegram_author(update)
                discord_uid = None
                if person_id:
                    try:
                        ids = await asyncio.to_thread(
                            identity_people.list_platform_identities_for_person, person_id,
                        )
                        discord_uid = next(
                            (i.platform_user_id for i in ids if i.platform == "discord"), None,
                        )
                    except Exception:
                        logger.exception("discord identity lookup failed for %s", person_id)
                if not discord_uid:
                    reply = (
                        "I don't have your Discord connected yet, so I can't message you there. "
                        "Connect it from your dashboard (Connect Discord → send the /link code to "
                        "the Cash bot), then I'll be able to."
                    )
                else:
                    try:
                        queue.enqueue_outbound("discord", current_tenant_id(), {
                            "platform_user_id": discord_uid,
                            "text": text,
                            "idempotency_key": uuid.uuid4().hex,
                        })
                        reply = "📨 On it — sending that to your Discord now."
                    except Exception as e:
                        logger.error("send_platform_message enqueue failed: %s", e)
                        reply = "😿 I couldn't queue that for Discord just now — try again in a moment."

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
            # The day the event currently lives on (defaults to today). Without
            # this, find_event only ever searched today's events, so moving
            # tomorrow's (or any other day's) event always failed to match.
            date_param = params.get("date", "today")
            target_date = _resolve_date((date_param or "today").strip().lower())
            # Optional target day to move the event TO (for "shift it to July 5").
            new_date_param = (params.get("new_date", "") or "").strip().lower()
            new_date = _resolve_date(new_date_param) if new_date_param else None
            # If AI didn't extract event_time, try extracting from user message
            if not event_time:
                event_time = _extract_time_from_text(user_msg)
                if event_time:
                    logger.info("Extracted time '%s' from user message as fallback", event_time)
            event = cal.find_event(title=event_title, event_time=event_time, date=target_date)
            if event and (new_time or new_date):
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
                        # Keep whichever of time/day the user didn't change.
                        new_start_time = dt.time.fromisoformat(new_time) if new_time else old_start.time()
                        new_start_date = new_date if new_date else old_start.date()
                        new_start = dt.datetime.combine(new_start_date, new_start_time)
                        result = cal.move_event(event["id"], new_start, duration, source=source)
                        if result:
                            when = new_start.strftime("%H:%M on %a, %b %d")
                            reply = f"📅 Moved '{event.get('summary')}' to {when} on {source.capitalize()} Calendar."
                        else:
                            reply = f"😿 Could not move '{event.get('summary')}' on {source.capitalize()} Calendar. The update failed on the calendar."
                    except Exception as e:
                        logger.error("Exception moving event '%s': %s", event.get("summary"), e)
                        reply = f"😿 Could not move '{event.get('summary')}' on {source.capitalize()} Calendar: {e}"
                else:
                    reply = f"😿 Could not move '{event.get('summary')}' — the event has no start time to work with."
            elif not event:
                desc = f"'{event_title}'" if event_title else f"at {event_time}"
                reply = f"😿 Could not find an event matching {desc} on {target_date}. No event was moved."
            else:
                reply = f"😿 No new time or date specified for '{event.get('summary')}'. Could not move the event."

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
                path = local_path_for(record)
                if not path or not os.path.exists(path):
                    reply = f"😿 The file '{record['name']}' is missing from storage."
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
            elif record.get("drive_web_link"):
                # Already on Drive — return the saved link, do NOT re-upload.
                existing = record.get("drive_short_link") or record["drive_web_link"]
                link_line = (
                    f"☁️ '{record['name']}' is already on your Drive.\n"
                    f"🔗 {existing}"
                )
                reply = f"{reply}\n\n{link_line}" if reply else link_line
            else:
                await update.message.reply_text(f"☁️ Uploading '{record['name']}' to Drive...")
                drive_file = None
                error_msg = ""
                try:
                    drive_file = upload_and_share(
                        local_path_for(record) or "",
                        record.get("name", "upload"),
                        record.get("mime_type", ""),
                    )
                except Exception as e:
                    logger.error("upload_to_drive failed: %s", e)
                    error_msg = str(e)

                if drive_file and drive_file.get("webViewLink"):
                    short = shorten_url(drive_file["webViewLink"])
                    # Remember the link so future asks reuse it instead of re-uploading.
                    set_drive_link(
                        record["id"],
                        drive_file_id=drive_file.get("id", ""),
                        web_view_link=drive_file["webViewLink"],
                        short_url=short,
                    )
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
                    short_link = ""
                    if target_cal == "google":
                        if record.get("drive_web_link"):
                            # Already on Drive — reuse the saved link, don't re-upload.
                            drive_file = {
                                "id": record.get("drive_file_id", ""),
                                "name": record.get("name", "upload"),
                                "mimeType": record.get("mime_type", ""),
                                "webViewLink": record["drive_web_link"],
                            }
                            short_link = record.get("drive_short_link") or shorten_url(record["drive_web_link"])
                        else:
                            await update.message.reply_text(f"☁️ Uploading '{record['name']}' to Drive...")
                            drive_file = upload_and_share(
                                local_path_for(record) or "",
                                record.get("name", "upload"),
                                record.get("mime_type", ""),
                            )
                            if drive_file and drive_file.get("webViewLink"):
                                short_link = shorten_url(drive_file["webViewLink"])
                                set_drive_link(
                                    record["id"],
                                    drive_file_id=drive_file.get("id", ""),
                                    web_view_link=drive_file["webViewLink"],
                                    short_url=short_link,
                                )

                    description_lines = [f"📎 {record['name']}"]
                    if short_link:
                        description_lines.append(f"Drive link: {short_link}")
                    else:
                        description_lines.append(f"Storage key: {record.get('storage_key', '')}")
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
        await _reply_typing(update.message, final_reply, context)
        log_message(
            "assistant", final_reply,
            metadata={"surface": "telegram", "person_id": person_id} if person_id else None,
        )

    except Exception as e:
        logger.error(f"Message handling error: {e}")
        await update.message.reply_text(f"Sorry, something went wrong: {e}")
