"""
task_tracker.py — Daily task list with persistence.
Tracks what's done, what's pending, and rolls over unfinished tasks.
"""

import json
import os
import datetime as dt
from typing import Optional

TASKS_DIR = "user_data/tasks"


def _today_path() -> str:
    os.makedirs(TASKS_DIR, exist_ok=True)
    return os.path.join(TASKS_DIR, f"{dt.date.today().isoformat()}.json")


def _load_tasks(date: Optional[dt.date] = None) -> list[dict]:
    path = os.path.join(TASKS_DIR, f"{(date or dt.date.today()).isoformat()}.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return []


def _save_tasks(tasks: list[dict], date: Optional[dt.date] = None):
    os.makedirs(TASKS_DIR, exist_ok=True)
    path = os.path.join(TASKS_DIR, f"{(date or dt.date.today()).isoformat()}.json")
    with open(path, "w") as f:
        json.dump(tasks, f, indent=2)


def initialize_daily_tasks(default_tasks: list[dict]) -> list[dict]:
    """
    Create today's task list from defaults + any rolled-over tasks from yesterday.
    Only runs once per day.
    """
    tasks = _load_tasks()
    if tasks:
        return tasks

    yesterday = dt.date.today() - dt.timedelta(days=1)
    yesterday_tasks = _load_tasks(yesterday)
    rollover = [
        {**t, "rolled_over": True, "done": False, "done_at": None}
        for t in yesterday_tasks
        if not t.get("done", False)
    ]

    today_tasks = []
    for i, t in enumerate(default_tasks):
        today_tasks.append({
            "id": i,
            "task": t["task"],
            "time": t.get("time", ""),
            "category": t.get("category", "general"),
            "done": False,
            "done_at": None,
            "rolled_over": False,
            "source": "default",
        })

    offset = len(today_tasks)
    for i, t in enumerate(rollover):
        t["id"] = offset + i
        t["source"] = "rollover"
        today_tasks.append(t)

    _save_tasks(today_tasks)
    return today_tasks


def add_task(task_text: str, time: str = "", category: str = "general") -> dict:
    """Add a new ad-hoc task to today's list."""
    tasks = _load_tasks()
    new_task = {
        "id": len(tasks),
        "task": task_text,
        "time": time,
        "category": category,
        "done": False,
        "done_at": None,
        "rolled_over": False,
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
            t["done_at"] = dt.datetime.now().isoformat()
            _save_tasks(tasks)
            return t
        if task_text and task_text.lower() in t["task"].lower():
            t["done"] = True
            t["done_at"] = dt.datetime.now().isoformat()
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
        for t in summary["pending"]:
            time_str = f" ({t['time']})" if t.get("time") else ""
            roll = " 🔄" if t.get("rolled_over") else ""
            lines.append(f"  □ [{t['id']}] {t['task']}{time_str}{roll}")

    if summary["done"]:
        lines.append("\n✅ DONE:")
        for t in summary["done"]:
            lines.append(f"  ✓ {t['task']}")

    return "\n".join(lines)
