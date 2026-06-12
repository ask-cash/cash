"""
queue.py — Redis-backed job queue decoupling ingestion from processing.

The gateway (Telegram webhooks) and the Discord connector are thin producers:
they validate, resolve the tenant, and enqueue a job. The worker pool consumes
jobs and does the expensive work (LLM calls, calendar/email I/O). This is what
lets api-gateway and worker scale independently under an HPA.

Job shape:
    {
      "type": "telegram_update" | "discord_event" | "cron",
      "tenant_id": "tnt_...",
      "payload": { ... },          # update json / event dict / cron spec
      "enqueued_at": "<iso8601>"
    }
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Optional

from services.config import settings

logger = logging.getLogger(__name__)

_redis = None

TELEGRAM_UPDATE = "telegram_update"
DISCORD_EVENT = "discord_event"
CRON = "cron"


def _client():
    global _redis
    if _redis is None:
        if not settings.redis_url:
            raise RuntimeError("REDIS_URL is not configured — queue unavailable")
        import redis

        _redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def enqueue(job_type: str, tenant_id: str, payload: dict) -> None:
    job = {
        "type": job_type,
        "tenant_id": tenant_id,
        "payload": payload,
        "enqueued_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    _client().lpush(settings.queue_name, json.dumps(job))


def dequeue(timeout: int = 5) -> Optional[dict]:
    """Blocking pop. Returns a job dict or None on timeout."""
    result = _client().brpop(settings.queue_name, timeout=timeout)
    if result is None:
        return None
    _, raw = result
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.error("Dropping malformed job: %r", raw[:200])
        return None


def ping() -> bool:
    try:
        return bool(_client().ping())
    except Exception:
        return False


def depth() -> int:
    try:
        return int(_client().llen(settings.queue_name))
    except Exception:
        return -1
