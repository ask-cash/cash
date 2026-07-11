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


def _int_or(env_name: str, default: int = 0) -> int:
    raw = (os.getenv(env_name) or "").strip()
    return int(raw) if raw.isdigit() else default


def _float_or(env_name: str, default: float = 0.0) -> float:
    raw = (os.getenv(env_name) or "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def _env_profile() -> dict:
    """Empty-by-default profile, overlaid with anything explicitly set in env.

    IMPORTANT: there are NO baked-in routine defaults. A fresh tenant that has
    not told Cash anything has an EMPTY schedule — no gym time, no trading hours,
    no wake/sleep. Cash must ask the user for their routine rather than assume
    one. Env vars only fill a field when an operator deliberately sets them
    (single-user / self-host convenience); absent env → empty.
    """
    gym_routine = {}
    for entry in _split(os.getenv("GYM_ROUTINE", ""), "|"):
        if ":" in entry:
            day, routine = entry.split(":", 1)
            gym_routine[day.strip()] = routine.strip()

    meals = []
    for entry in _split(os.getenv("DIET_MEALS", ""), "|"):
        parts = entry.split(",", 2)
        if len(parts) == 3:
            meals.append({"time": parts[0].strip(), "name": parts[1].strip(), "items": parts[2].strip()})

    default_tasks = []
    for entry in _split(os.getenv("DEFAULT_TASKS", ""), "|"):
        parts = entry.split(",", 2)
        if len(parts) == 3:
            default_tasks.append({
                "time": parts[0].strip(),
                "category": parts[1].strip(),
                "task": parts[2].strip(),
            })

    return {
        "name": os.getenv("USER_NAME", ""),
        "timezone": os.getenv("TIMEZONE", "Asia/Kolkata"),
        "wake_time": os.getenv("WAKE_TIME", ""),
        "sleep_time": os.getenv("SLEEP_TIME", ""),

        "gym": {
            "default_time": os.getenv("GYM_TIME", ""),
            "duration_minutes": _int_or("GYM_DURATION_MINUTES", 0),
            "commute_minutes": _int_or("GYM_COMMUTE_MINUTES", 0),
            "gym_closes_at": os.getenv("GYM_CLOSES_AT", ""),
            "days": _split(os.getenv("GYM_DAYS", "")),
            "routine": gym_routine,
        },

        "diet": {
            "meals": meals,
            "water_goal_liters": _float_or("WATER_GOAL_LITERS", 0.0),
            "supplements": _split(os.getenv("SUPPLEMENTS", "")),
        },

        "trading": {
            "market_open": os.getenv("MARKET_OPEN", ""),
            "market_close": os.getenv("MARKET_CLOSE", ""),
            "pre_market_review_time": os.getenv("PRE_MARKET_REVIEW", ""),
            "rules": _split(os.getenv("TRADING_RULES", ""), "|"),
        },

        "default_tasks": default_tasks,
    }


def has_routine(profile: dict) -> bool:
    """True if the user has told Cash any routine (gym/trading/wake/sleep/tasks)."""
    gym = profile.get("gym", {}) or {}
    trading = profile.get("trading", {}) or {}
    return any([
        profile.get("wake_time"), profile.get("sleep_time"),
        gym.get("default_time"), gym.get("days"), gym.get("routine"),
        trading.get("market_open"), trading.get("rules"),
        profile.get("default_tasks"),
    ])


def _empty_profile() -> dict:
    """A blank profile skeleton with NO env overlay — the starting point for a
    tenant that hasn't told Cash anything (e.g. a fresh web signup)."""
    return {
        "name": "",
        "timezone": "Asia/Kolkata",
        "wake_time": "",
        "sleep_time": "",
        "gym": {"default_time": "", "duration_minutes": 0, "commute_minutes": 0,
                "gym_closes_at": "", "days": [], "routine": {}},
        "diet": {"meals": [], "water_goal_liters": 0.0, "supplements": []},
        "trading": {"market_open": "", "market_close": "", "pre_market_review_time": "", "rules": []},
        "default_tasks": [],
    }


def load_profile() -> dict:
    """The owner's profile for the active tenant.

    The env-provided routine belongs ONLY to the self-host/default tenant. Every
    other tenant (a web signup, another customer) starts from an EMPTY profile so
    one person's routine, gym, and trading rules never bleed into another's. On
    top of the base we overlay the tenant record (name + timezone) and the
    per-tenant ``profile/owner`` document, which is where each user's own profile
    is built and saved. Best-effort — falls back to a usable profile on error.
    """
    from services.tenancy import current_tenant_id as _tid
    from services.config import settings as _settings

    profile = _env_profile() if _tid() == _settings.default_tenant_id else _empty_profile()
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
