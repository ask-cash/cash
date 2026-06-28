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

# Outbound (Cash-initiated) delivery: separate per-(platform, tenant) lists so a
# connector pops only the work for the platform it owns a live client for. This
# is the spine of cross-platform send (design: cash-cross-platform-presence.md §2).
OUTBOUND_PREFIX = "cash:outbound"


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


def _outbound_key(platform: str, tenant_id: str) -> str:
    return f"{OUTBOUND_PREFIX}:{platform}:{tenant_id}"


def enqueue_outbound(platform: str, tenant_id: str, payload: dict) -> None:
    """Queue a Cash-initiated message for delivery by the platform's connector.

    ``payload`` carries the destination + text, e.g.
    ``{"to": "owner", "text": "...", "idempotency_key": "<uuid>"}`` or an explicit
    ``{"platform_user_id": "123", ...}``. The connector resolves "owner" against
    the id it already holds, so producers don't need the platform's user id.
    """
    job = {
        "platform": platform,
        "tenant_id": tenant_id,
        "payload": payload,
        "enqueued_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    _client().lpush(_outbound_key(platform, tenant_id), json.dumps(job))


def dequeue_outbound(platform: str, tenant_id: str, timeout: int = 5) -> Optional[dict]:
    """Blocking pop of one outbound job for (platform, tenant). None on timeout.

    Synchronous/blocking — call from a thread (``asyncio.to_thread``) inside an
    event loop so the connector's gateway socket isn't starved.
    """
    result = _client().brpop(_outbound_key(platform, tenant_id), timeout=timeout)
    if result is None:
        return None
    _, raw = result
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.error("Dropping malformed outbound job: %r", raw[:200])
        return None


def claim_idempotency(key: str, ttl_seconds: int = 86400) -> bool:
    """Atomically claim an idempotency key. True if newly claimed, False if seen.

    Backs at-most-once delivery across redelivery/retries. Fails open (returns
    True) if Redis is unreachable — a possible duplicate message beats dropping
    a delivery the user asked for.
    """
    if not key:
        return True
    try:
        return bool(_client().set(f"{OUTBOUND_PREFIX}:idem:{key}", "1", nx=True, ex=ttl_seconds))
    except Exception:
        logger.exception("idempotency claim failed for %s", key)
        return True


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
