"""Disposable PostgreSQL + Redis integration smoke used by CI/CD.

This module deliberately stays outside ``test_*.py`` discovery because it
requires dedicated services. Run only with ``CASH_INTEGRATION_TEST=1`` against
an empty test database and Redis instance.
"""

from __future__ import annotations

import os
import uuid

from services import conversations, queue, rate_limits
from services.config import settings
from services.db import bootstrap, connect
from services.tenancy import tenant_context


def _require_disposable_services() -> None:
    if os.getenv("CASH_INTEGRATION_TEST") != "1":
        raise SystemExit("Refusing to run without CASH_INTEGRATION_TEST=1.")
    if not settings.database_url.startswith(("postgres://", "postgresql://")):
        raise SystemExit("A disposable PostgreSQL DATABASE_URL is required.")
    if not settings.redis_url:
        raise SystemExit("A disposable REDIS_URL is required.")


def _fake_interpreter(message: str, **kwargs) -> dict:
    assert kwargs["surface"] == "dashboard"
    assert kwargs["model"] == "claude-haiku-4-5-20251001"
    return {"reply": f"processed: {message}", "action": "chat"}


def _postgres_smoke(suffix: str) -> None:
    tenant_a = f"integration-a-{suffix}"
    tenant_b = f"integration-b-{suffix}"
    request_id = f"request-{suffix}"

    with tenant_context(tenant_a):
        conversation = conversations.create_conversation(
            model_id="claude-haiku-4-5-20251001"
        )
        job = conversations.prepare_job(
            f"person-{suffix}",
            tenant_a,
            conversation["id"],
            "postgres integration",
            model_id="claude-haiku-4-5-20251001",
            client_request_id=request_id,
        )
        result = conversations.process_job(
            tenant_a,
            job["id"],
            interpret=_fake_interpreter,
        )
        assert result["reply"] == "processed: postgres integration"
        assert conversations.get_job(job["id"])["status"] == "complete"
        with connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 1

    with tenant_context(tenant_b):
        assert conversations.get_conversation(conversation["id"]) is None
        with connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 0
            policies = conn.execute(
                "SELECT COUNT(*) FROM pg_policies "
                "WHERE policyname = 'tenant_isolation'"
            ).fetchone()[0]
            assert policies >= 15


def _redis_smoke(suffix: str) -> None:
    first = queue.enqueue(
        queue.CHAT_MESSAGE,
        f"integration-{suffix}",
        {"job_id": f"job-{suffix}"},
        idempotency_key=f"chat:integration:{suffix}",
    )
    duplicate = queue.enqueue(
        queue.CHAT_MESSAGE,
        f"integration-{suffix}",
        {"job_id": f"job-{suffix}"},
        idempotency_key=f"chat:integration:{suffix}",
    )
    assert duplicate == first

    delivery = queue.dequeue(timeout=1, consumer=f"integration-1-{suffix}")
    assert delivery and delivery["payload"]["job_id"] == f"job-{suffix}"
    queue.touch(delivery, f"integration-1-{suffix}")
    queue.defer(delivery)

    deferred = queue.dequeue(timeout=1, consumer=f"integration-2-{suffix}")
    assert deferred and deferred["payload"]["job_id"] == f"job-{suffix}"
    assert queue.retry_or_dead_letter(deferred, "transient") is True

    retried = queue.dequeue(timeout=1, consumer=f"integration-3-{suffix}")
    assert retried and retried["attempt"] == 1
    queue.ack(retried)

    rate_limits.check(f"integration-{suffix}", limit=1)
    try:
        rate_limits.check(f"integration-{suffix}", limit=1)
    except rate_limits.RateLimitExceeded:
        pass
    else:
        raise AssertionError("Distributed request limiting was not enforced.")

    with rate_limits.concurrency(
        f"integration-{suffix}",
        limit=1,
        lease_seconds=30,
    ):
        try:
            with rate_limits.concurrency(
                f"integration-{suffix}",
                limit=1,
                lease_seconds=30,
            ):
                raise AssertionError("Distributed capacity limit was not enforced.")
        except rate_limits.ConcurrencyLimitExceeded:
            pass


def main() -> None:
    _require_disposable_services()
    bootstrap()
    suffix = uuid.uuid4().hex[:12]
    _postgres_smoke(suffix)
    _redis_smoke(suffix)
    print("PostgreSQL RLS/durable chat and Redis Streams integration passed")


if __name__ == "__main__":
    main()
