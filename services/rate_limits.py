"""Small distributed fixed-window limits for authenticated dashboard work."""

from __future__ import annotations

import contextlib
import threading
import time
import uuid

from services.config import settings


class RateLimitExceeded(RuntimeError):
    def __init__(self, retry_after: int):
        super().__init__("Too many requests. Please wait a moment and try again.")
        self.retry_after = max(1, int(retry_after))


class RateLimitUnavailable(RuntimeError):
    pass


class ConcurrencyLimitExceeded(RuntimeError):
    pass


_memory: dict[str, tuple[int, float]] = {}
_guard = threading.Lock()
_active: dict[str, int] = {}


def check(key: str, *, limit: int, window_seconds: int = 60) -> None:
    if limit <= 0:
        return
    now = time.time()
    bucket = int(now // window_seconds)
    redis_key = f"cash:rate:{key}:{bucket}"

    if settings.redis_url:
        try:
            from services import queue

            client = queue.redis_client()
            pipe = client.pipeline()
            pipe.incr(redis_key)
            pipe.expire(redis_key, window_seconds + 2, nx=True)
            count, _ = pipe.execute()
        except Exception as exc:
            raise RateLimitUnavailable("Request limiting is temporarily unavailable.") from exc
        if int(count) > limit:
            retry = window_seconds - int(now % window_seconds)
            raise RateLimitExceeded(retry)
        return

    # Local development fallback. Bound stale entries opportunistically.
    with _guard:
        count, expires = _memory.get(redis_key, (0, now + window_seconds))
        if expires <= now:
            count, expires = 0, now + window_seconds
        count += 1
        _memory[redis_key] = (count, expires)
        if len(_memory) > 2_000:
            for stale in [k for k, (_, expiry) in _memory.items() if expiry <= now]:
                _memory.pop(stale, None)
    if count > limit:
        raise RateLimitExceeded(max(1, int(expires - now)))


@contextlib.contextmanager
def concurrency(
    key: str,
    *,
    limit: int,
    lease_seconds: int,
):
    """Reserve bounded provider capacity across gateway and worker replicas."""
    if limit <= 0:
        yield
        return
    token = uuid.uuid4().hex
    redis_key = f"cash:concurrency:{key}"
    local = not settings.redis_url
    if local:
        with _guard:
            current = _active.get(redis_key, 0)
            if current >= limit:
                raise ConcurrencyLimitExceeded(
                    "Cash is at capacity for this operation. Try again shortly."
                )
            _active[redis_key] = current + 1
    else:
        now_ms = int(time.time() * 1000)
        lease_ms = max(1, int(lease_seconds)) * 1000
        try:
            from services import queue

            acquired = queue.redis_client().eval(
                """
                redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
                if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[2]) then
                    return 0
                end
                redis.call('ZADD', KEYS[1], ARGV[3], ARGV[4])
                redis.call('PEXPIRE', KEYS[1], ARGV[5])
                return 1
                """,
                1,
                redis_key,
                now_ms,
                limit,
                now_ms + lease_ms,
                token,
                lease_ms + 60_000,
            )
        except Exception as exc:
            raise RateLimitUnavailable(
                "Provider capacity coordination is temporarily unavailable."
            ) from exc
        if not acquired:
            raise ConcurrencyLimitExceeded(
                "Cash is at capacity for this operation. Try again shortly."
            )
    try:
        yield
    finally:
        if local:
            with _guard:
                remaining = max(0, _active.get(redis_key, 1) - 1)
                if remaining:
                    _active[redis_key] = remaining
                else:
                    _active.pop(redis_key, None)
        else:
            try:
                from services import queue

                queue.redis_client().zrem(redis_key, token)
            except Exception:
                # The lease expires automatically; never hide the real result.
                pass
