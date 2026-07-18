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
import hashlib
import json
import logging
import os
import socket
import threading
from typing import Optional

from services.config import settings

logger = logging.getLogger(__name__)

_redis = None

TELEGRAM_UPDATE = "telegram_update"
DISCORD_EVENT = "discord_event"
CRON = "cron"
CHAT_MESSAGE = "chat_message"
MEDIA_TRANSCRIPTION = "media_transcription"

_STREAM_SUFFIX = ":stream:v2"
_GROUP = os.getenv("QUEUE_CONSUMER_GROUP", "cash-workers")
_claim_counter = 0
_claim_lock = threading.Lock()

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

        _redis = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=float(
                os.getenv("REDIS_CONNECT_TIMEOUT_SECONDS", "5")
            ),
            # Must remain longer than the queue's blocking read (five seconds).
            socket_timeout=float(os.getenv("REDIS_SOCKET_TIMEOUT_SECONDS", "10")),
            socket_keepalive=True,
            health_check_interval=30,
            retry_on_timeout=True,
        )
    return _redis


def redis_client():
    """Shared Redis client for locks/rate limits; callers must not close it."""
    return _client()


def _stream_key() -> str:
    # Keep the stream separate from the legacy Redis list so a rolling deploy
    # never hits WRONGTYPE while older workers finish their existing queue.
    return f"{settings.queue_name}{_STREAM_SUFFIX}"


def _ensure_group() -> None:
    try:
        _client().xgroup_create(_stream_key(), _GROUP, id="0-0", mkstream=True)
    except Exception as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def enqueue(
    job_type: str,
    tenant_id: str,
    payload: dict,
    *,
    idempotency_key: str = "",
) -> str:
    job = {
        "type": job_type,
        "tenant_id": tenant_id,
        "payload": payload,
        "enqueued_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "attempt": 0,
    }
    _ensure_group()
    encoded = json.dumps(job)
    created = True
    if idempotency_key:
        digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
        dedupe_key = f"{_stream_key()}:enqueue:{digest}"
        stream_id, created_raw = _client().eval(
            """
            local existing = redis.call('GET', KEYS[2])
            if existing then
                return {existing, '0'}
            end
            local stream_id = redis.call('XADD', KEYS[1], '*', 'job', ARGV[1])
            redis.call('SET', KEYS[2], stream_id, 'EX', ARGV[2])
            return {stream_id, '1'}
            """,
            2,
            _stream_key(),
            dedupe_key,
            encoded,
            int(os.getenv("QUEUE_ENQUEUE_DEDUPE_SECONDS", "604800")),
        )
        created = str(created_raw) == "1"
    else:
        stream_id = _client().xadd(
            _stream_key(),
            {"job": encoded},
        )
    try:
        from app.observability import JOBS_ENQUEUED

        if created:
            JOBS_ENQUEUED.labels(type=job_type).inc()
    except Exception:
        pass
    return str(stream_id)


def _decode_stream_message(stream_id: str, fields: dict) -> Optional[dict]:
    raw = fields.get("job", "")
    try:
        job = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("Malformed stream job %s: %r", stream_id, raw[:200])
        return None
    job["_queue_id"] = str(stream_id)
    return job


def _claim_stale(consumer: str) -> Optional[dict]:
    global _claim_counter
    with _claim_lock:
        _claim_counter += 1
        should_claim = _claim_counter % int(os.getenv("QUEUE_CLAIM_EVERY", "20")) == 0
    if not should_claim:
        return None
    try:
        result = _client().xautoclaim(
            _stream_key(),
            _GROUP,
            consumer,
            min_idle_time=int(os.getenv("QUEUE_STALE_AFTER_MS", "300000")),
            start_id="0-0",
            count=1,
        )
        messages = result[1] if len(result) > 1 else []
        if messages:
            stream_id, fields = messages[0]
            return _decode_stream_message(stream_id, fields)
    except Exception:
        logger.exception("Failed to reclaim a stale queue job")
    return None


def dequeue(timeout: int = 5, consumer: str = "") -> Optional[dict]:
    """Read one acknowledged stream job. Call :func:`ack` after success."""
    _ensure_group()
    consumer = consumer or f"{socket.gethostname()}-{os.getpid()}-{threading.get_ident()}"
    stale = _claim_stale(consumer)
    if stale is not None:
        return stale
    result = _client().xreadgroup(
        _GROUP,
        consumer,
        {_stream_key(): ">"},
        count=1,
        block=max(1, int(timeout * 1000)),
    )
    if not result:
        # Drain jobs produced by an older gateway during a rolling v1→v2
        # deployment. New producers always write the acknowledged stream.
        legacy = _client().rpop(settings.queue_name)
        if not legacy:
            return None
        try:
            return json.loads(legacy)
        except json.JSONDecodeError:
            logger.error("Dropping malformed legacy job: %r", legacy[:200])
            return None
    _, messages = result[0]
    if not messages:
        return None
    stream_id, fields = messages[0]
    job = _decode_stream_message(stream_id, fields)
    if job is None:
        _client().xack(_stream_key(), _GROUP, stream_id)
        _client().xdel(_stream_key(), stream_id)
    return job


def ack(job: dict) -> None:
    stream_id = job.get("_queue_id")
    if not stream_id:
        return
    pipe = _client().pipeline()
    pipe.xack(_stream_key(), _GROUP, stream_id)
    pipe.xdel(_stream_key(), stream_id)
    pipe.execute()


def touch(job: dict, consumer: str) -> None:
    """Refresh a live delivery's idle timer so XAUTOCLAIM cannot duplicate it."""
    stream_id = job.get("_queue_id")
    if not stream_id:
        return
    _client().xclaim(
        _stream_key(),
        _GROUP,
        consumer,
        min_idle_time=0,
        message_ids=[stream_id],
        justid=True,
    )


def defer(job: dict) -> None:
    """Move a later conversation turn behind currently runnable stream work."""
    stream_id = job.get("_queue_id")
    clean = {
        key: value for key, value in job.items()
        if not key.startswith("_")
    }
    clean["deferred_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    pipe = _client().pipeline()
    if stream_id:
        pipe.xack(_stream_key(), _GROUP, stream_id)
        pipe.xdel(_stream_key(), stream_id)
    pipe.xadd(_stream_key(), {"job": json.dumps(clean)})
    pipe.execute()


def retry_or_dead_letter(job: dict, error: str = "") -> bool:
    """Acknowledge the failed delivery and enqueue a bounded retry.

    Returns True when requeued, False when moved to the dead-letter stream.
    """
    stream_id = job.get("_queue_id")
    attempt = int(job.get("attempt") or 0) + 1
    clean = {
        key: value for key, value in job.items()
        if not key.startswith("_")
    }
    clean["attempt"] = attempt
    clean["last_error"] = (error or "")[:500]
    clean["retried_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    max_attempts = int(os.getenv("QUEUE_MAX_ATTEMPTS", "3"))
    pipe = _client().pipeline()
    if stream_id:
        pipe.xack(_stream_key(), _GROUP, stream_id)
        pipe.xdel(_stream_key(), stream_id)
    if attempt < max_attempts:
        pipe.xadd(
            _stream_key(),
            {"job": json.dumps(clean)},
        )
        requeued = True
    else:
        pipe.xadd(
            f"{_stream_key()}:dead",
            {"job": json.dumps(clean)},
            maxlen=int(os.getenv("QUEUE_DLQ_MAXLEN", "10000")),
            approximate=True,
        )
        requeued = False
    pipe.execute()
    return requeued


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
        client = _client()
        return int(client.xlen(_stream_key())) + int(client.llen(settings.queue_name))
    except Exception:
        return -1
