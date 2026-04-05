"""
scheduler.py — Smart conflict resolution engine.
Resolves overlaps between calendar events and your routines (gym, meals, etc).
"""

import datetime as dt
from services.user_profile import load_profile


def resolve_conflicts(events: list[dict], profile: dict = None) -> list[dict]:
    """
    Given today's calendar events + user profile, find conflicts with
    routines (gym, meals) and suggest resolutions.
    """
    if profile is None:
        profile = load_profile()

    suggestions = []
    gym = profile.get("gym", {})

    gym_start_str = gym.get("default_time", "07:30")
    gym_duration = gym.get("duration_minutes", 60)
    gym_commute = gym.get("commute_minutes", 15)
    gym_closes = gym.get("gym_closes_at", "22:00")

    today = dt.date.today()
    gym_start = dt.datetime.combine(today, dt.time.fromisoformat(gym_start_str))
    gym_end = gym_start + dt.timedelta(minutes=gym_duration + gym_commute)
    gym_close_dt = dt.datetime.combine(today, dt.time.fromisoformat(gym_closes))

    for ev in events:
        ev_start_raw = ev.get("start", {}).get("dateTime")
        ev_end_raw = ev.get("end", {}).get("dateTime")
        if not ev_start_raw:
            continue

        ev_start = dt.datetime.fromisoformat(ev_start_raw)
        ev_end = dt.datetime.fromisoformat(ev_end_raw) if ev_end_raw else ev_start + dt.timedelta(hours=1)
        ev_title = ev.get("summary", "Untitled")

        if ev_start < gym_end and ev_end > gym_start:
            proposed_gym_start = ev_end + dt.timedelta(minutes=gym_commute)
            proposed_gym_end = proposed_gym_start + dt.timedelta(minutes=gym_duration)
            feasible = proposed_gym_end <= gym_close_dt

            for other_ev in events:
                if other_ev is ev:
                    continue
                o_start_raw = other_ev.get("start", {}).get("dateTime")
                o_end_raw = other_ev.get("end", {}).get("dateTime")
                if o_start_raw:
                    o_start = dt.datetime.fromisoformat(o_start_raw)
                    o_end = dt.datetime.fromisoformat(o_end_raw) if o_end_raw else o_start + dt.timedelta(hours=1)
                    if proposed_gym_start < o_end and o_start < proposed_gym_end:
                        proposed_gym_start = o_end + dt.timedelta(minutes=gym_commute)
                        proposed_gym_end = proposed_gym_start + dt.timedelta(minutes=gym_duration)
                        feasible = proposed_gym_end <= gym_close_dt

            suggestions.append({
                "type": "move_gym",
                "reason": f"'{ev_title}' at {ev_start.strftime('%H:%M')} overlaps with gym at {gym_start_str}",
                "suggestion": f"Move gym to {proposed_gym_start.strftime('%H:%M')}",
                "new_time": proposed_gym_start.strftime("%H:%M"),
                "new_start": proposed_gym_start.isoformat(),
                "feasible": feasible,
                "note": "" if feasible else "⚠️ Gym closes before you'd finish. Consider skipping or doing a shorter session.",
            })

    diet = profile.get("diet", {})
    for meal in diet.get("meals", []):
        meal_time = dt.datetime.combine(today, dt.time.fromisoformat(meal["time"]))
        meal_end = meal_time + dt.timedelta(minutes=30)
        for ev in events:
            ev_start_raw = ev.get("start", {}).get("dateTime")
            if not ev_start_raw:
                continue
            ev_start = dt.datetime.fromisoformat(ev_start_raw)
            ev_end_raw = ev.get("end", {}).get("dateTime")
            ev_end = dt.datetime.fromisoformat(ev_end_raw) if ev_end_raw else ev_start + dt.timedelta(hours=1)
            if ev_start < meal_end and ev_end > meal_time:
                suggestions.append({
                    "type": "meal_conflict",
                    "reason": f"'{ev.get('summary', '?')}' overlaps with {meal['name']} at {meal['time']}",
                    "suggestion": f"Have {meal['name']} before or after the event",
                    "feasible": True,
                })

    return suggestions


def format_suggestions(suggestions: list[dict]) -> str:
    if not suggestions:
        return "✅ No schedule conflicts found. You're good!"

    lines = ["⚠️ Schedule Conflicts Detected:\n"]
    for i, s in enumerate(suggestions, 1):
        lines.append(f"{i}. {s['reason']}")
        lines.append(f"   → {s['suggestion']}")
        if s.get("note"):
            lines.append(f"   {s['note']}")
        lines.append("")
    return "\n".join(lines)
