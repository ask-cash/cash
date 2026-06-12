"""
worker.py — Job queue consumer that runs the actual bot logic.

Pulls jobs the gateway/connector enqueued and processes each inside the right
tenant context (so the data layer's RLS and the secret vault resolve to that
tenant). Telegram updates are dispatched through a per-tenant
python-telegram-bot Application (no polling — we feed updates directly).

This is the workload that scales out under an HPA: add replicas to drain a
deeper queue. It holds no client sockets, so any replica can process any
tenant's job.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict

from telegram import Update
from telegram.ext import Application

from app.observability import JOB_DURATION, JOBS_PROCESSED, configure_logging
from bot.app_factory import build_application
from services import queue
from services import secrets as secret_vault
from services import tenant_registry
from services.db import bootstrap
from services.memory import log_message
from services.tenancy import tenant_context

configure_logging()
logger = logging.getLogger(__name__)

# Per-tenant initialized PTB Applications, reused across jobs.
_apps: Dict[str, Application] = {}
_apps_lock = asyncio.Lock()


async def _get_application(tenant_id: str) -> Application | None:
    async with _apps_lock:
        app = _apps.get(tenant_id)
        if app is not None:
            return app

        token = tenant_registry.get_bot_token(tenant_id, "telegram")
        if not token:
            logger.error("No telegram token for tenant %s", tenant_id)
            return None

        owner_raw = secret_vault.get_secret("owner_telegram_id", tenant_id=tenant_id)
        owner_id = int(owner_raw) if owner_raw and owner_raw.isdigit() else 0

        app = build_application(token, owner_id=owner_id)
        await app.initialize()
        _apps[tenant_id] = app
        logger.info("Initialized PTB application for tenant %s", tenant_id)
        return app


async def _handle_telegram_update(tenant_id: str, payload: dict) -> None:
    app = await _get_application(tenant_id)
    if app is None:
        return
    update = Update.de_json(payload, app.bot)
    await app.process_update(update)


async def _handle_discord_event(tenant_id: str, payload: dict) -> None:
    """Lightweight async work for a Discord event (memory/identity).

    Replies are sent by the connector that owns the live socket; here we only
    persist to the tenant's memory so it shows up in future context.
    """
    text = payload.get("content", "")
    author = payload.get("author_name", "someone")
    if text:
        log_message(
            "user",
            f"[discord] {author}: {text}",
            metadata={"surface": "discord", "person_id": payload.get("person_id")},
        )


async def _handle_cron(tenant_id: str, payload: dict) -> None:
    from app import cron

    await cron.run_job(payload.get("job", ""), tenant_id)


async def _dispatch(job: dict) -> None:
    job_type = job.get("type", "")
    tenant_id = job.get("tenant_id", "")
    payload = job.get("payload", {})
    if not tenant_id:
        logger.warning("job missing tenant_id: %s", job_type)
        return

    with JOB_DURATION.labels(type=job_type).time():
        try:
            with tenant_context(tenant_id):
                if job_type == queue.TELEGRAM_UPDATE:
                    await _handle_telegram_update(tenant_id, payload)
                elif job_type == queue.DISCORD_EVENT:
                    await _handle_discord_event(tenant_id, payload)
                elif job_type == queue.CRON:
                    await _handle_cron(tenant_id, payload)
                else:
                    logger.warning("unknown job type %r", job_type)
                    return
            JOBS_PROCESSED.labels(type=job_type, status="ok").inc()
        except Exception:
            logger.exception("job failed: type=%s tenant=%s", job_type, tenant_id)
            JOBS_PROCESSED.labels(type=job_type, status="error").inc()


async def run() -> None:
    bootstrap()
    logger.info("worker started — consuming %s", queue.settings.queue_name)
    loop = asyncio.get_running_loop()
    while True:
        # queue.dequeue blocks on Redis; run it off the event loop.
        job = await loop.run_in_executor(None, queue.dequeue, 5)
        if job is not None:
            await _dispatch(job)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
