"""
gateway.py — Stateless FastAPI ingress.

Responsibilities (all cheap, no LLM/I/O work — that's the worker's job):
  * Receive Telegram webhook updates at POST /tg/{token}, authenticate them,
    resolve the bot token to a tenant, and enqueue the update.
  * Expose health/readiness/metrics for Kubernetes probes + Prometheus.
  * Provide a small admin API to onboard a tenant and register its Telegram
    bot (which also calls setWebhook so Telegram starts delivering here).

Because it holds no per-connection state and does no long-polling, this scales
horizontally behind an HPA — the whole point of the K8s move.
"""

from __future__ import annotations

import logging
import os

import requests
from fastapi import FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel

from app.observability import (
    QUEUE_DEPTH,
    WEBHOOK_REQUESTS,
    configure_logging,
)
from services import queue
from services.config import settings
from services.db import bootstrap, is_postgres
from services import tenant_registry
from services.tenancy import system_context, tenant_context

configure_logging()
logger = logging.getLogger(__name__)

ADMIN_TOKEN = os.getenv("ADMIN_API_TOKEN", "")

app = FastAPI(title="Cash Gateway", version="1.0.0")


@app.on_event("startup")
def _startup() -> None:
    bootstrap()
    logger.info("gateway started (postgres=%s)", is_postgres())


# ---------------------------------------------------------------------------
# Health / metrics
# ---------------------------------------------------------------------------

@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    ok_queue = queue.ping()
    if not ok_queue:
        raise HTTPException(status_code=503, detail="queue unavailable")
    return {"status": "ready", "queue": ok_queue}


@app.get("/metrics")
def metrics():
    try:
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

        QUEUE_DEPTH.set(queue.depth())
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
    except Exception:
        return Response("metrics unavailable", status_code=503)


# ---------------------------------------------------------------------------
# Telegram webhook
# ---------------------------------------------------------------------------

@app.post("/tg/{token}")
async def telegram_webhook(
    token: str,
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    if settings.telegram_webhook_secret and x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        WEBHOOK_REQUESTS.labels(platform="telegram", status="unauthorized").inc()
        raise HTTPException(status_code=401, detail="bad webhook secret")

    with system_context():
        tenant_id = tenant_registry.resolve_tenant_by_token("telegram", token)
    if not tenant_id:
        WEBHOOK_REQUESTS.labels(platform="telegram", status="unknown_tenant").inc()
        raise HTTPException(status_code=404, detail="unknown bot")

    update = await request.json()
    queue.enqueue(queue.TELEGRAM_UPDATE, tenant_id, update)
    WEBHOOK_REQUESTS.labels(platform="telegram", status="accepted").inc()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Admin / onboarding
# ---------------------------------------------------------------------------

class TenantOnboard(BaseModel):
    display_name: str = ""
    timezone: str = "Asia/Kolkata"
    telegram_bot_token: str = ""
    owner_telegram_id: int = 0


def _require_admin(token: str | None) -> None:
    if not ADMIN_TOKEN or token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="admin auth required")


@app.post("/admin/tenants")
def create_tenant(body: TenantOnboard, x_admin_token: str | None = Header(default=None)):
    _require_admin(x_admin_token)
    tenant_id = tenant_registry.new_tenant_id()
    with system_context():
        tenant_registry.ensure_tenant(
            tenant_id, display_name=body.display_name, timezone=body.timezone
        )
        if body.telegram_bot_token:
            tenant_registry.register_bot(
                tenant_id=tenant_id, platform="telegram", token=body.telegram_bot_token
            )

    if body.telegram_bot_token:
        if body.owner_telegram_id:
            with tenant_context(tenant_id):
                from services import secrets as secret_vault

                secret_vault.set_secret("owner_telegram_id", str(body.owner_telegram_id))
        _set_telegram_webhook(body.telegram_bot_token)

    return {"tenant_id": tenant_id}


def _set_telegram_webhook(token: str) -> None:
    """Point Telegram at this gateway for the given bot token."""
    if not settings.public_base_url:
        logger.warning("PUBLIC_BASE_URL unset — skipping setWebhook")
        return
    url = f"{settings.public_base_url.rstrip('/')}/tg/{token}"
    payload = {"url": url}
    if settings.telegram_webhook_secret:
        payload["secret_token"] = settings.telegram_webhook_secret
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/setWebhook", json=payload, timeout=10
        )
        logger.info("setWebhook -> %s %s", resp.status_code, resp.text[:200])
    except Exception:
        logger.exception("setWebhook failed")
