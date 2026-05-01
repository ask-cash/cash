"""
availability.py — Why Suhail probably isn't responding right now.

Used by the Discord proxy responder to compose a contextual reply when Suhail
hasn't answered a mention within the proxy delay window.

Privacy: event titles are sanitized to coarse labels by default ("in a
meeting", "on a call"). To opt an event into raw-title disclosure, add the
tag `[cash:public]` anywhere in the event description.
"""

import datetime as dt
import logging
import re
from dataclasses import dataclass
from typing import Optional

from calendars.unified import UnifiedCalendar
from services.user_profile import get_tz, load_profile

logger = logging.getLogger(__name__)

PUBLIC_TAG = "[cash:public]"
DEFAULT_BUSY_LABEL = "in a meeting"

# Keyword → label rules. First match wins.
_TITLE_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(1[:-]?1|one[- ]on[- ]one)\b", re.I), "in a 1:1"),
    (re.compile(r"\binterview", re.I), "in an interview"),
    (re.compile(r"\bstand[- ]?up", re.I), "in standup"),
    (re.compile(r"\b(retro|retrospective)\b", re.I), "in a retro"),
    (re.compile(r"\bre+view\b", re.I), "in a review"),
    (re.compile(r"\b(call|sync|huddle)\b", re.I), "on a call"),
    (re.compile(r"\b(focus|deep[- ]?work|heads[- ]?down)\b", re.I), "in a focus block"),
    (re.compile(r"\b(lunch|dinner|breakfast)\b", re.I), "at a meal"),
    (re.compile(r"\b(gym|workout)\b", re.I), "at the gym"),
]


@dataclass
class AvailabilityReason:
    busy: bool
    label: str                                # human-readable, sanitized
    until: Optional[dt.datetime] = None       # when the current commitment ends
    free_after: Optional[dt.datetime] = None  # best guess of when Suhail is next free
    working_hours: bool = True


_calendar: Optional[UnifiedCalendar] = None


def _calendar_instance() -> UnifiedCalendar:
    global _calendar
    if _calendar is None:
        _calendar = UnifiedCalendar()
    return _calendar


def _sanitize_title(event: dict) -> str:
    summary = event.get("summary") or ""
    description = event.get("description") or ""
    if PUBLIC_TAG in description:
        return summary or DEFAULT_BUSY_LABEL
    for pattern, label in _TITLE_RULES:
        if pattern.search(summary):
            return label
    return DEFAULT_BUSY_LABEL


def _event_window(event: dict) -> Optional[tuple[dt.datetime, dt.datetime]]:
    start_raw = event.get("start", {}).get("dateTime")
    end_raw = event.get("end", {}).get("dateTime")
    if not start_raw or not end_raw:
        return None
    try:
        return dt.datetime.fromisoformat(start_raw), dt.datetime.fromisoformat(end_raw)
    except ValueError:
        return None


def _next_free_after(events: list[dict], busy_end: dt.datetime) -> dt.datetime:
    """Walk subsequent events to find the first gap after busy_end (back-to-back chains)."""
    candidate = busy_end
    # Iterate until no event consumes the candidate moment — handles chains.
    advanced = True
    while advanced:
        advanced = False
        for ev in events:
            win = _event_window(ev)
            if not win:
                continue
            start, end = win
            if start <= candidate < end:
                candidate = end
                advanced = True
    return candidate


def _parse_hhmm(value: Optional[str], default: str) -> dt.time:
    try:
        return dt.time.fromisoformat(value or default)
    except (ValueError, TypeError):
        return dt.time.fromisoformat(default)


def _working_hours_check(at_local: dt.datetime) -> tuple[bool, Optional[dt.datetime]]:
    """Return (within_working_hours, next_wake_datetime_if_outside).

    Assumes wake_time < sleep_time on the same day (i.e. doesn't wrap past
    midnight). All known profiles satisfy this.
    """
    profile = load_profile()
    tz = get_tz()
    wake = _parse_hhmm(profile.get("wake_time"), "06:30")
    sleep = _parse_hhmm(profile.get("sleep_time"), "23:00")

    today_wake = dt.datetime.combine(at_local.date(), wake, tzinfo=tz)
    today_sleep = dt.datetime.combine(at_local.date(), sleep, tzinfo=tz)

    if today_wake <= at_local < today_sleep:
        return True, None

    next_wake_date = at_local.date() if at_local < today_wake else at_local.date() + dt.timedelta(days=1)
    next_wake = dt.datetime.combine(next_wake_date, wake, tzinfo=tz)
    return False, next_wake


def explain_unavailability(at: Optional[dt.datetime] = None) -> AvailabilityReason:
    """Why Suhail probably isn't responding at the given moment.

    `at` may be naive or aware; naive values are interpreted in the user's tz.
    Calendar/IO failures degrade gracefully to the working-hours-only path.
    """
    tz = get_tz()
    if at is None:
        at = dt.datetime.now(tz)
    if at.tzinfo is None:
        at = at.replace(tzinfo=tz)
    at_local = at.astimezone(tz)

    cal = _calendar_instance()
    try:
        events = cal.get_events_for_date(at_local.date())
    except Exception:
        logger.exception("availability: failed to fetch events; falling back to working-hours only")
        events = []

    # 1. Currently in an event?
    for ev in events:
        win = _event_window(ev)
        if not win:
            continue
        start, end = win
        if start <= at < end:
            return AvailabilityReason(
                busy=True,
                label=_sanitize_title(ev),
                until=end,
                free_after=_next_free_after(events, end),
                working_hours=True,
            )

    # 2. Outside working hours?
    in_hours, next_wake = _working_hours_check(at_local)
    if not in_hours:
        return AvailabilityReason(
            busy=True,
            label="off the clock",
            until=next_wake,
            free_after=next_wake,
            working_hours=False,
        )

    # 3. In hours, no event — probably just AFK.
    return AvailabilityReason(
        busy=False,
        label="probably just away from his desk",
        working_hours=True,
    )


def format_local_time(when: Optional[dt.datetime]) -> str:
    """Render a tz-aware datetime as e.g. '4:30 PM' in the user's timezone."""
    if when is None:
        return ""
    if when.tzinfo is None:
        when = when.replace(tzinfo=get_tz())
    return when.astimezone(get_tz()).strftime("%-I:%M %p").lstrip("0")
