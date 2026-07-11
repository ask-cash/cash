"""calendar pack — viewing and editing the user's calendar."""

from services.skills.registry import Skill, register

SKILL = register(Skill(
    id="calendar",
    title="Calendar",
    order=20,
    actions=(
        "show_schedule", "show_tomorrow", "show_date", "check_conflicts",
        "move_event", "create_event", "create_recurring_events", "delete_event",
    ),
    flag="calendar",
    prompt='''- "show_schedule" — show today's schedule (params: {})
- "show_tomorrow" — show tomorrow's schedule (params: {})
- "show_date" — show the schedule for a SPECIFIC day the user names (e.g. "what's on July 6", "show Friday", "events on 2026-07-06"). Use this WHENEVER the user asks about a day that is NOT today or tomorrow. params: {"date": "YYYY-MM-DD"} — ALWAYS a concrete date resolved from the UPCOMING DATES table. (For today use show_schedule; for tomorrow use show_tomorrow.)
- "check_conflicts" — resolve schedule conflicts (params: {})
- "move_event" — reschedule an existing event to a new time and/or a new day (params: {"event_title": "...", "event_time": "HH:MM" (24h — the event's CURRENT start time if referenced by time), "date": "today|tomorrow|YYYY-MM-DD" (the day the event is CURRENTLY on — REQUIRED so it can be found; default "today"), "new_time": "HH:MM" (omit if only the day changes), "new_date": "today|tomorrow|YYYY-MM-DD" (the day to move it TO — omit if only the time changes)}). Provide at least one of new_time / new_date. Resolve every relative day to a concrete date using the UPCOMING DATES table. If the event the user refers to is in the CALENDAR block above, read its current day/time from there.
- "create_event" — create calendar event (params: {"title": "...", "date": "YYYY-MM-DD", "start_time": "HH:MM", "duration_minutes": N, "calendar": "google|outlook"})
  IMPORTANT: "date" must ALWAYS be a concrete YYYY-MM-DD string. Resolve relative references yourself using CURRENT TIME above. "today" → today's date, "tomorrow" → tomorrow's date, "Wednesday" → the next upcoming Wednesday's date, "next Friday" → next Friday's date. NEVER pass words like "today" or "wednesday" — always convert to YYYY-MM-DD.
- "create_recurring_events" — create a SERIES of events spaced a fixed number of days apart, all in ONE action. ALWAYS use this (never repeated create_event) whenever the user asks for repeating/recurring events or several events at an interval — e.g. "every 14 days", "weekly for 8 weeks", "sets 1 to 13". params: {"title_template": "Change Braces Set - {n}", "start_date": "YYYY-MM-DD", "start_time": "HH:MM", "duration_minutes": N, "interval_days": 14, "count": 13, "calendar": "google|outlook"}
  - Put the literal token {n} in title_template to number each occurrence (1..count). Omit {n} for identical titles on every occurrence.
  - start_date is the FIRST occurrence (concrete YYYY-MM-DD). The system computes the rest as start_date + interval_days*i. Do NOT enumerate the dates yourself.
  - count is the total number of events (max 60). The system creates them and reports exactly how many succeeded — your "reply" is replaced by that authoritative result, so do NOT list the dates or claim success in "reply"; just say you're creating them.
- "delete_event" — delete/remove a calendar event (params: {"event_title": "...", "event_time": "HH:MM" (24h format, include if the user references the event by time e.g. "the 9 am event" → "09:00"), "date": "today|tomorrow|YYYY-MM-DD", "source": "google|outlook|auto"})''',
))
