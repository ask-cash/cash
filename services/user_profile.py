"""
user_profile.py — Loads ALL your defaults from .env so you configure once.
No separate JSON to maintain. Everything lives in environment variables.
"""

import os
import datetime as dt
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()


def get_tz() -> ZoneInfo:
    """Get the user's configured timezone."""
    return ZoneInfo(os.getenv("TIMEZONE", "Asia/Kolkata"))


def now() -> dt.datetime:
    """Current datetime in user's timezone."""
    return dt.datetime.now(get_tz())


def today() -> dt.date:
    """Current date in user's timezone."""
    return now().date()


def _split(val: str, sep: str = ",") -> list[str]:
    if not val:
        return []
    return [x.strip() for x in val.split(sep) if x.strip()]


def load_profile() -> dict:
    """Build the full profile dict from environment variables."""

    # Parse gym routine: "Mon:Chest + Triceps|Tue:Back + Biceps|..."
    gym_routine = {}
    for entry in _split(os.getenv("GYM_ROUTINE", ""), "|"):
        if ":" in entry:
            day, routine = entry.split(":", 1)
            gym_routine[day.strip()] = routine.strip()

    # Parse meals: "07:00,Pre-workout,Banana + coffee|09:00,Breakfast,Eggs oats"
    meals = []
    for entry in _split(os.getenv("DIET_MEALS", ""), "|"):
        parts = entry.split(",", 2)
        if len(parts) == 3:
            meals.append({"time": parts[0].strip(), "name": parts[1].strip(), "items": parts[2].strip()})

    # Parse default tasks: "06:35,wellness,Morning meditation|08:45,trading,Review watchlist"
    default_tasks = []
    for entry in _split(os.getenv("DEFAULT_TASKS", ""), "|"):
        parts = entry.split(",", 2)
        if len(parts) == 3:
            default_tasks.append({
                "time": parts[0].strip(),
                "category": parts[1].strip(),
                "task": parts[2].strip(),
            })

    # Parse trading rules: "Rule one|Rule two|Rule three"
    trading_rules = _split(os.getenv("TRADING_RULES", ""), "|")

    return {
        "name": os.getenv("USER_NAME", "User"),
        "timezone": os.getenv("TIMEZONE", "Asia/Kolkata"),
        "wake_time": os.getenv("WAKE_TIME", "06:30"),
        "sleep_time": os.getenv("SLEEP_TIME", "23:00"),

        "gym": {
            "default_time": os.getenv("GYM_TIME", "07:30"),
            "duration_minutes": int(os.getenv("GYM_DURATION_MINUTES", "60")),
            "commute_minutes": int(os.getenv("GYM_COMMUTE_MINUTES", "15")),
            "gym_closes_at": os.getenv("GYM_CLOSES_AT", "22:00"),
            "days": _split(os.getenv("GYM_DAYS", "Mon,Tue,Wed,Thu,Fri,Sat")),
            "routine": gym_routine,
        },

        "diet": {
            "meals": meals,
            "water_goal_liters": float(os.getenv("WATER_GOAL_LITERS", "3.5")),
            "supplements": _split(os.getenv("SUPPLEMENTS", "")),
        },

        "trading": {
            "market_open": os.getenv("MARKET_OPEN", "09:15"),
            "market_close": os.getenv("MARKET_CLOSE", "15:30"),
            "pre_market_review_time": os.getenv("PRE_MARKET_REVIEW", "08:45"),
            "rules": trading_rules,
        },

        "default_tasks": default_tasks,
    }
