"""
observability.py — Logging + Prometheus metrics shared by all roles.
"""

from __future__ import annotations

import logging
import sys

from services.config import settings

try:
    from prometheus_client import Counter, Gauge, Histogram
    _PROM = True
except Exception:  # pragma: no cover - metrics optional
    _PROM = False


def configure_logging() -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    if settings.log_json:
        fmt = '{"level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}'
    else:
        fmt = "%(asctime)s %(levelname)s %(name)s %(message)s"
    logging.basicConfig(level=level, format=fmt, stream=sys.stdout, force=True)


if _PROM:
    JOBS_ENQUEUED = Counter(
        "cash_jobs_enqueued_total", "Jobs enqueued", ["type"]
    )
    JOBS_PROCESSED = Counter(
        "cash_jobs_processed_total", "Jobs processed", ["type", "status"]
    )
    JOB_DURATION = Histogram(
        "cash_job_duration_seconds", "Job processing duration", ["type"]
    )
    QUEUE_DEPTH = Gauge("cash_queue_depth", "Current job queue depth")
    CONNECTOR_SOCKETS = Gauge(
        "cash_connector_sockets", "Active Discord gateway sockets on this pod"
    )
    WEBHOOK_REQUESTS = Counter(
        "cash_webhook_requests_total", "Inbound webhook requests", ["platform", "status"]
    )
else:  # pragma: no cover - no-op shims so callers don't branch everywhere
    class _Noop:
        def labels(self, *a, **k):
            return self

        def inc(self, *a, **k):
            pass

        def observe(self, *a, **k):
            pass

        def set(self, *a, **k):
            pass

        def time(self):
            from contextlib import nullcontext

            return nullcontext()

    JOBS_ENQUEUED = JOBS_PROCESSED = JOB_DURATION = _Noop()
    QUEUE_DEPTH = CONNECTOR_SOCKETS = WEBHOOK_REQUESTS = _Noop()
