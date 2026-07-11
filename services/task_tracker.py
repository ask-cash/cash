"""
task_tracker.py — Daily task list with persistence.
Tracks what's done, what's pending, and rolls over unfinished tasks.

Tasks are stored per-day as tenant-scoped JSON documents via
services.state_store (namespace "tasks", key = ISO date).
"""

import datetime as dt
from typing import Optional

from services import state_store
from services.user_profile import now as ist_now, today as ist_today

NAMESPACE = "tasks"

# Priority tiers, 0 = highest. Kept small and human ("do this first" → 0).
_TIER_BADGE = {0: "🔴", 1: "🟠", 2: "", 3: "🔵"}


def _age_days(first_seen: str) -> int:
    """Whole days a task has been alive, from its first_seen ISO date."""
    try:
        seen = dt.date.fromisoformat((first_seen or "")[:10])
        return max((ist_today() - seen).days, 0)
    except ValueError:
        return 0


def _load_tasks(date: Optional[dt.date] = None) -> list[dict]:
    key = (date or ist_today()).isoformat()
    return state_store.read_json(NAMESPACE, key, default=[])


def _save_tasks(tasks: list[dict], date: Optional[dt.date] = None):
    key = (date or ist_today()).isoformat()
    state_store.write_json(NAMESPACE, key, tasks)


def initialize_daily_tasks(default_tasks: list[dict]) -> list[dict]:
    """
    Create today's task list from defaults + any rolled-over tasks from yesterday.
    Only runs once per day.
    """
    tasks = _load_tasks()
    if tasks:
        return tasks

    yesterday = ist_today() - dt.timedelta(days=1)
    yesterday_tasks = _load_tasks(yesterday)
    rollover = [
        {
            **t,
            "rolled_over": True,
            "done": False,
            "done_at": None,
            # Formalized rollover history: count how many days it's followed you,
            # and preserve when it first appeared so age is stable across days.
            "rollover_count": t.get("rollover_count", 0) + 1,
            "first_seen": t.get("first_seen", yesterday.isoformat()),
        }
        for t in yesterday_tasks
        if not t.get("done", False)
    ]

    today_str = ist_today().isoformat()
    today_tasks = []
    for i, t in enumerate(default_tasks):
        today_tasks.append({
            "id": i,
            "task": t["task"],
            "time": t.get("time", ""),
            "category": t.get("category", "general"),
            "priority_tier": t.get("priority_tier", 2),
            "done": False,
            "done_at": None,
            "rolled_over": False,
            "rollover_count": 0,
            "first_seen": today_str,
            "source": "default",
        })

    offset = len(today_tasks)
    for i, t in enumerate(rollover):
        t["id"] = offset + i
        t["source"] = "rollover"
        today_tasks.append(t)

    _save_tasks(today_tasks)
    return today_tasks


def add_task(task_text: str, time: str = "", category: str = "general",
             priority_tier: int = 2) -> dict:
    """Add a new ad-hoc task to today's list."""
    tasks = _load_tasks()
    new_task = {
        "id": len(tasks),
        "task": task_text,
        "time": time,
        "category": category,
        "priority_tier": priority_tier,
        "done": False,
        "done_at": None,
        "rolled_over": False,
        "rollover_count": 0,
        "first_seen": ist_today().isoformat(),
        "source": "manual",
    }
    tasks.append(new_task)
    _save_tasks(tasks)
    return new_task


def mark_done(task_id: int = None, task_text: str = None) -> Optional[dict]:
    """Mark a task as done by ID or by fuzzy text match."""
    tasks = _load_tasks()
    for t in tasks:
        if task_id is not None and t["id"] == task_id:
            t["done"] = True
            t["done_at"] = ist_now().isoformat()
            _save_tasks(tasks)
            return t
        if task_text and task_text.lower() in t["task"].lower():
            t["done"] = True
            t["done_at"] = ist_now().isoformat()
            _save_tasks(tasks)
            return t
    return None


def get_tasks_summary() -> dict:
    """Return a summary of today's tasks."""
    tasks = _load_tasks()
    done = [t for t in tasks if t.get("done")]
    pending = [t for t in tasks if not t.get("done")]
    return {
        "total": len(tasks),
        "done": done,
        "pending": pending,
        "done_count": len(done),
        "pending_count": len(pending),
    }


def format_tasks() -> str:
    """Pretty-print today's tasks."""
    summary = get_tasks_summary()
    lines = [f"📋 Tasks — {summary['done_count']}/{summary['total']} done\n"]

    if summary["pending"]:
        lines.append("⏳ PENDING:")
        # Highest priority (lowest tier) first, then oldest first.
        pending = sorted(
            summary["pending"],
            key=lambda t: (t.get("priority_tier", 2), -_age_days(t.get("first_seen", ""))),
        )
        for t in pending:
            time_str = f" ({t['time']})" if t.get("time") else ""
            badge = _TIER_BADGE.get(t.get("priority_tier", 2), "")
            badge = f"{badge} " if badge else ""
            age = _age_days(t.get("first_seen", ""))
            if t.get("rolled_over") and age > 0:
                roll = f" 🔄 day {age + 1}"
            else:
                roll = ""
            lines.append(f"  □ {badge}[{t['id']}] {t['task']}{time_str}{roll}")

    if summary["done"]:
        lines.append("\n✅ DONE:")
        for t in summary["done"]:
            lines.append(f"  ✓ {t['task']}")

    return "\n".join(lines)
