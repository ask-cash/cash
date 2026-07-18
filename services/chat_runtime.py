"""Concurrency controls for ordered, idempotent conversation processing."""

from __future__ import annotations

import contextlib
import os
import threading
import time
import uuid

from services.config import settings


class ConversationBusyError(RuntimeError):
    pass


_locks: dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()


def _local_lock(key: str) -> threading.RLock:
    with _locks_guard:
        return _locks.setdefault(key, threading.RLock())


@contextlib.contextmanager
def conversation_lock(tenant_id: str, conversation_id: str):
    """Serialize turns within a conversation across threads and production pods."""
    key = f"cash:chat:lock:{tenant_id}:{conversation_id}"
    if not settings.redis_url:
        lock = _local_lock(key)
        acquired = lock.acquire(timeout=float(os.getenv("CHAT_LOCK_WAIT_SECONDS", "5")))
        if not acquired:
            raise ConversationBusyError("This conversation is already processing a message.")
        try:
            yield
        finally:
            lock.release()
        return

    from services import queue

    client = queue.redis_client()
    token = uuid.uuid4().hex
    wait_seconds = float(os.getenv("CHAT_LOCK_WAIT_SECONDS", "5"))
    ttl_seconds = int(os.getenv("CHAT_LOCK_TTL_SECONDS", "600"))
    deadline = time.monotonic() + wait_seconds
    acquired = False
    while time.monotonic() < deadline:
        try:
            acquired = bool(client.set(key, token, nx=True, ex=ttl_seconds))
        except Exception as exc:
            # In a Redis-configured production deployment, failing open could run
            # the same tool twice on two pods. Reject the turn instead.
            raise ConversationBusyError("Chat coordination is temporarily unavailable.") from exc
        if acquired:
            break
        time.sleep(0.05)
    if not acquired:
        raise ConversationBusyError("Cash is still finishing the previous message in this chat.")
    renew_stop = threading.Event()

    def _renew() -> None:
        interval = max(1.0, ttl_seconds / 3)
        while not renew_stop.wait(interval):
            try:
                client.eval(
                    "if redis.call('get', KEYS[1]) == ARGV[1] then "
                    "return redis.call('expire', KEYS[1], ARGV[2]) else return 0 end",
                    1,
                    key,
                    token,
                    ttl_seconds,
                )
            except Exception:
                # A safely large base TTL remains the fallback during a brief
                # Redis interruption. The worker stream lease is renewed too.
                pass

    renewer = threading.Thread(
        target=_renew,
        name=f"cash-chat-lock-{conversation_id[:12]}",
        daemon=True,
    )
    renewer.start()
    try:
        yield
    finally:
        renew_stop.set()
        renewer.join(timeout=1)
        try:
            client.eval(
                "if redis.call('get', KEYS[1]) == ARGV[1] then "
                "return redis.call('del', KEYS[1]) else return 0 end",
                1,
                key,
                token,
            )
        except Exception:
            # The expiry is the final safety net; never mask a completed reply.
            pass
