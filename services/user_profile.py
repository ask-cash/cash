"""
user_profile.py — The owner's profile (name, timezone, routines, rules).

Source of truth is the DATABASE, per tenant: the `tenants` record (name +
timezone) plus a per-tenant ``profile/owner`` document in the kv store for the
richer fields. ``.env`` provides only the bootstrap defaults used when the DB
has nothing yet, so a fresh deployment still works before onboarding writes a
profile. Precedence (low → high): env defaults < tenant record < profile doc.
"""

import os
import logging
import datetime as dt
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_PROFILE_NS = "profile"
_PROFILE_KEY = "owner"


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


def _merge(base: dict, override: dict) -> None:
    """Deep-merge ``override`` into ``base`` in place (dicts recurse)."""
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        elif v not in (None, ""):
            base[k] = v


def _env_profile() -> dict:
    """Bootstrap defaults from environment variables (used when DB is empty)."""

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


def load_profile() -> dict:
    """The owner's profile for the active tenant.

    Starts from env defaults, then overlays the DB: the tenant record (name +
    timezone) and the per-tenant ``profile/owner`` document. Best-effort — if
    the DB or tenant context is unavailable we fall back to env so callers always
    get a usable profile.
    """
    profile = _env_profile()
    try:
        from services import state_store
        from services.tenancy import current_tenant_id

        try:
            from services import tenant_registry
            rec = tenant_registry.get_tenant(current_tenant_id())
            if rec:
                # Skip placeholder display names like "Default" — not a person.
                if rec.display_name and rec.display_name.strip().lower() != "default":
                    profile["name"] = rec.display_name
                if getattr(rec, "timezone", ""):
                    profile["timezone"] = rec.timezone
        except Exception:
            logger.debug("load_profile: tenant record overlay skipped", exc_info=True)

        stored = state_store.read_json(_PROFILE_NS, _PROFILE_KEY, default=None)
        if isinstance(stored, dict) and stored:
            _merge(profile, stored)
    except Exception:
        logger.debug("load_profile: DB overlay unavailable, using env defaults", exc_info=True)
    return profile


def save_profile(updates: dict) -> dict:
    """Persist owner-profile overrides to the per-tenant DB doc; return merged profile."""
    from services import state_store

    stored = state_store.read_json(_PROFILE_NS, _PROFILE_KEY, default={}) or {}
    _merge(stored, updates)
    state_store.write_json(_PROFILE_NS, _PROFILE_KEY, stored)
    return load_profile()
