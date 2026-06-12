"""
cron.py — Scheduled fan-out jobs.

Replaces the in-process job_queue (main.py) with Kubernetes CronJobs. Each
CronJob runs `python -m app cron <job_name>`, which enqueues one CRON job per
active tenant; the worker then executes `run_job(job_name, tenant_id)` inside
that tenant's context. This keeps scheduling reliable and tenant-isolated as
the tenant count grows.

Supported jobs mirror the original scheduler:
  morning_briefing, trading_reminder, evening_summary, email_check,
  directive_expiry, summary_rollup
"""

from __future__ import annotations

import logging

from services import queue
from services import secrets as secret_vault
from services import tenant_registry
from services.db import bootstrap
from services.tenancy import system_context, tenant_context
from services.user_profile import load_profile

logger = logging.getLogger(__name__)

JOBS = {
    "morning_briefing",
    "trading_reminder",
    "evening_summary",
    "email_check",
    "directive_expiry",
    "summary_rollup",
}


# ---------------------------------------------------------------------------
# Fan-out: enqueue one CRON job per tenant (run from the CronJob pod).
# ---------------------------------------------------------------------------

def fan_out(job_name: str) -> int:
    if job_name not in JOBS:
        raise SystemExit(f"unknown cron job {job_name!r}; expected one of {sorted(JOBS)}")
    bootstrap()
    count = 0
    with system_context():
        tenants = tenant_registry.list_tenants(active_only=True)
    for tenant in tenants:
        queue.enqueue(queue.CRON, tenant.tenant_id, {"job": job_name})
        count += 1
    logger.info("cron '%s' fanned out to %d tenant(s)", job_name, count)
    return count


# ---------------------------------------------------------------------------
# Execution: run a single tenant's job (called by the worker).
# ---------------------------------------------------------------------------

async def run_job(job_name: str, tenant_id: str) -> None:
    handler = _HANDLERS.get(job_name)
    if handler is None:
        logger.warning("no handler for cron job %r", job_name)
        return
    with tenant_context(tenant_id):
        await handler(tenant_id)


def _owner_id(tenant_id: str) -> int:
    raw = secret_vault.get_secret("owner_telegram_id", tenant_id=tenant_id)
    return int(raw) if raw and raw.isdigit() else 0


async def _send(tenant_id: str, text: str) -> None:
    owner_id = _owner_id(tenant_id)
    token = tenant_registry.get_bot_token(tenant_id, "telegram")
    if not owner_id or not token:
        logger.info("skip send for %s (owner/token missing)", tenant_id)
        return
    from telegram import Bot

    async with Bot(token) as bot:
        await bot.send_message(chat_id=owner_id, text=text)


async def _morning_briefing(tenant_id: str) -> None:
    from calendars.unified import UnifiedCalendar
    from services.ai_brain import generate_briefing
    from services.scheduler import resolve_conflicts, format_suggestions
    from services.task_tracker import initialize_daily_tasks, format_tasks

    profile = load_profile()
    cal = UnifiedCalendar()
    events = cal.get_today_events(profile.get("timezone", "Asia/Kolkata"))
    events_text = cal.format_events(events)
    initialize_daily_tasks(profile.get("default_tasks", []))
    tasks_text = format_tasks()
    suggestions = resolve_conflicts(events, profile)
    conflicts_text = format_suggestions(suggestions)
    briefing = generate_briefing(events_text, tasks_text, conflicts_text)
    await _send(tenant_id, f"😼 Morning. {briefing}")


async def _trading_reminder(tenant_id: str) -> None:
    profile = load_profile()
    rules = profile.get("trading", {}).get("rules", [])
    if not rules:
        return
    text = "😾 Market opens soon. The rules:\n\n" + "\n".join(
        f"{i}. {r}" for i, r in enumerate(rules, 1)
    )
    await _send(tenant_id, text + "\n\nNo revenge trading. I'm watching. 🐾")


async def _evening_summary(tenant_id: str) -> None:
    from services.task_tracker import initialize_daily_tasks, get_tasks_summary

    profile = load_profile()
    initialize_daily_tasks(profile.get("default_tasks", []))
    summary = get_tasks_summary()
    ratio = f"{summary['done_count']}/{summary['total']}"
    text = f"🌙 End of day — {ratio} tasks done."
    if summary["pending"]:
        text += "\n\nRolling over:\n" + "\n".join(f"  • {t['task']}" for t in summary["pending"])
    await _send(tenant_id, text)


async def _email_check(tenant_id: str) -> None:
    from services.email_classifier import classify_emails, is_email_seen, mark_email_seen
    from services.gmail import GmailManager

    try:
        gmail = GmailManager()
    except Exception:
        logger.info("gmail not connected for %s", tenant_id)
        return
    emails = gmail.fetch_unread_emails(max_results=10)
    new_emails = [e for e in emails if not is_email_seen(e["id"])]
    if not new_emails:
        return
    classified = classify_emails(new_emails)
    for e in classified:
        mark_email_seen(e["id"], e.get("classification", "low_priority"))
    important = [e for e in classified if e.get("classification") == "important"]
    if not important:
        return
    text = f"📬 {len(important)} new important email(s):\n\n" + "\n".join(
        f"• {e['from_name']}: {e['subject'][:60]}" for e in important[:5]
    )
    await _send(tenant_id, text)


async def _directive_expiry(tenant_id: str) -> None:
    import asyncio

    from services.directives import store as directives_store

    count = await asyncio.to_thread(directives_store.expire_due)
    if count:
        logger.info("[cron] expired %d directive(s) for %s", count, tenant_id)


async def _summary_rollup(tenant_id: str) -> None:
    import asyncio

    from services.identity import summaries

    rebuilt = await asyncio.to_thread(summaries.rebuild_stale)
    logger.info("[cron] summary rollup for %s rebuilt %d", tenant_id, rebuilt)


_HANDLERS = {
    "morning_briefing": _morning_briefing,
    "trading_reminder": _trading_reminder,
    "evening_summary": _evening_summary,
    "email_check": _email_check,
    "directive_expiry": _directive_expiry,
    "summary_rollup": _summary_rollup,
}
