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
import contextlib
import logging
import os
import signal
import socket
import time
from typing import Dict

from telegram import Update
from telegram.ext import Application

from app.observability import JOB_DURATION, JOBS_PROCESSED, configure_logging
from bot.app_factory import build_application
from services import queue
from services import rate_limits
from services.conversations import ChatJobDeferred, ChatJobTerminalError
from services import secrets as secret_vault
from services import tenant_registry
from services.chat_runtime import ConversationBusyError
from services.config import settings
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


async def _handle_chat_message(tenant_id: str, payload: dict) -> None:
    from services import conversations

    job_id = payload.get("job_id", "")
    if not job_id:
        raise ValueError("chat job missing job_id")
    with rate_limits.concurrency(
        "chat-provider",
        limit=int(os.getenv("CHAT_GLOBAL_CONCURRENCY", "80")),
        lease_seconds=int(os.getenv("CHAT_CONCURRENCY_LEASE_SECONDS", "720")),
    ):
        await asyncio.to_thread(conversations.process_job, tenant_id, job_id)


async def _handle_media_transcription(tenant_id: str, payload: dict) -> None:
    from services import attachments, storage, transcription

    attachment_id = payload.get("attachment_id", "")
    if not attachment_id:
        raise ValueError("media transcription job missing attachment_id")
    record = attachments.get_attachment(attachment_id, include_private=True)
    if record is None or record.get("status") in {"ready", "failed"}:
        return
    attachments.mark_transcription_enqueued(attachment_id)
    path = await asyncio.to_thread(
        storage.local_path_for,
        record["storage_key"],
        suffix=os.path.splitext(record["name"])[1],
    )
    if path is None:
        # A user may delete a draft while a worker is picking it up.
        if attachments.get_attachment(attachment_id) is None:
            return
        raise FileNotFoundError("media attachment object is unavailable")
    cleanup = settings.storage_backend.lower() in {"s3", "gcs"}
    try:
        await asyncio.to_thread(transcription.validate_media_duration, path)
        with rate_limits.concurrency(
            "transcription",
            limit=int(os.getenv("TRANSCRIPTION_GLOBAL_CONCURRENCY", "20")),
            lease_seconds=int(
                os.getenv("TRANSCRIPTION_CONCURRENCY_LEASE_SECONDS", "180")
            ),
        ):
            transcript = await asyncio.to_thread(
                transcription.transcribe_path,
                path,
                filename=record["name"],
                mime_type=record["mimeType"],
            )
        try:
            attachments.set_transcript(attachment_id, transcript)
        except attachments.AttachmentError:
            # Deletion won the race after the provider completed; there is no
            # remaining attachment to retry or mark failed.
            if attachments.get_attachment(attachment_id) is None:
                return
            raise
    finally:
        if cleanup:
            with contextlib.suppress(OSError):
                os.remove(path)


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
                elif job_type == queue.CHAT_MESSAGE:
                    await _handle_chat_message(tenant_id, payload)
                elif job_type == queue.MEDIA_TRANSCRIPTION:
                    await _handle_media_transcription(tenant_id, payload)
                else:
                    raise ValueError(f"unknown job type {job_type!r}")
            JOBS_PROCESSED.labels(type=job_type, status="ok").inc()
        except Exception as exc:
            status = (
                "deferred"
                if isinstance(
                    exc,
                    (
                        ChatJobDeferred,
                        ConversationBusyError,
                        rate_limits.ConcurrencyLimitExceeded,
                    ),
                )
                else "error"
            )
            JOBS_PROCESSED.labels(type=job_type, status=status).inc()
            raise


async def _renew_delivery(job: dict, consumer_name: str) -> None:
    interval = max(5, int(os.getenv("QUEUE_HEARTBEAT_SECONDS", "60")))
    while True:
        await asyncio.sleep(interval)
        try:
            await asyncio.to_thread(queue.touch, job, consumer_name)
        except Exception:
            logger.exception("failed to renew queue delivery lease")


def _flush_dispatch_outbox() -> None:
    """Publish committed work with one bounded control-plane query."""
    from services import dispatch_outbox

    for entry in dispatch_outbox.pending(limit=200):
        queue.enqueue(
            entry["jobType"],
            entry["tenantId"],
            entry["payload"],
            idempotency_key=entry["id"],
        )
        dispatch_outbox.mark_delivered(entry["id"])


async def _consumer(index: int, stopping: asyncio.Event) -> None:
    consumer_name = f"{socket.gethostname()}-{os.getpid()}-{index}"
    loop = asyncio.get_running_loop()
    last_outbox_flush = 0.0
    while not stopping.is_set():
        if index == 0 and time.monotonic() - last_outbox_flush >= 5:
            try:
                await asyncio.to_thread(_flush_dispatch_outbox)
            except Exception:
                logger.exception("failed to flush durable background work")
            last_outbox_flush = time.monotonic()
        job = await loop.run_in_executor(
            None,
            queue.dequeue,
            5,
            consumer_name,
        )
        if job is None:
            continue
        lease_task = (
            asyncio.create_task(_renew_delivery(job, consumer_name))
            if job.get("_queue_id")
            else None
        )
        try:
            try:
                await _dispatch(job)
            except (
                ChatJobDeferred,
                ConversationBusyError,
                rate_limits.ConcurrencyLimitExceeded,
            ):
                # Redis transactions atomically ACK the current delivery and put
                # it behind earlier turns without spending its retry budget.
                await asyncio.sleep(
                    float(os.getenv("CAPACITY_DEFER_SECONDS", "1"))
                )
                queue.defer(job)
            except ChatJobTerminalError:
                queue.ack(job)
            except Exception as exc:
                logger.exception(
                    "job failed: type=%s tenant=%s attempt=%s",
                    job.get("type"),
                    job.get("tenant_id"),
                    job.get("attempt", 0),
                )
                try:
                    await asyncio.sleep(
                        min(10.0, float(2 ** int(job.get("attempt", 0))))
                    )
                    requeued = queue.retry_or_dead_letter(job, str(exc))
                except Exception:
                    # Leave the message pending; XAUTOCLAIM will recover it after
                    # the worker or Redis connection stabilises.
                    logger.exception("failed to retry/dead-letter queue job")
                    continue
                if not requeued and job.get("type") == queue.CHAT_MESSAGE:
                    try:
                        from services import conversations

                        with tenant_context(job.get("tenant_id", "")):
                            conversations.fail_job(
                                (job.get("payload") or {}).get("job_id", ""),
                                "Cash could not complete this message after several attempts.",
                            )
                    except Exception:
                        logger.exception("failed to mark exhausted chat job")
                elif not requeued and job.get("type") == queue.MEDIA_TRANSCRIPTION:
                    try:
                        from services import attachments

                        with tenant_context(job.get("tenant_id", "")):
                            attachments.set_failed(
                                (job.get("payload") or {}).get(
                                    "attachment_id",
                                    "",
                                )
                            )
                    except Exception:
                        logger.exception(
                            "failed to mark exhausted media transcription"
                        )
            else:
                try:
                    queue.ack(job)
                except Exception:
                    # Processing is idempotent; leave pending for recovery rather
                    # than deleting a response we cannot prove was acknowledged.
                    logger.exception("failed to acknowledge queue job")
        finally:
            if lease_task is not None:
                lease_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await lease_task


async def run() -> None:
    bootstrap()
    from prometheus_client import start_http_server

    # This endpoint doubles as the worker's lightweight process-health socket.
    start_http_server(int(os.getenv("WORKER_METRICS_PORT", "9000")))
    concurrency = max(1, int(os.getenv("WORKER_CONCURRENCY", "8")))
    logger.info(
        "worker started — consuming %s with concurrency=%d",
        settings.queue_name,
        concurrency,
    )
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(signum, stopping.set)
        except (NotImplementedError, RuntimeError):
            pass
    await asyncio.gather(
        *(_consumer(index, stopping) for index in range(concurrency))
    )
    logger.info("worker drained and stopped")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
