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
from fastapi.responses import HTMLResponse, RedirectResponse
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


# ---------------------------------------------------------------------------
# Customer onboarding — secure web setup
# ---------------------------------------------------------------------------

def _onboard_payload_or_404(token: str) -> dict:
    from services.onboarding import links as onboarding_links

    payload = onboarding_links.verify_token(token)
    if not payload:
        raise HTTPException(status_code=404, detail="invalid or expired link")
    return payload


def _render_setup_page(token: str, profile) -> str:
    from services.onboarding.profiles import KNOWN_INTEGRATIONS

    labels = {
        "google_calendar": "Google Calendar",
        "google_drive": "Google Drive",
        "gmail": "Gmail",
        "outlook": "Outlook Calendar",
    }
    rows = []
    for key in KNOWN_INTEGRATIONS:
        connected = bool((profile.integrations or {}).get(key))
        badge = "✅ Connected" if connected else (
            f'<a class="btn" href="/onboard/{token}/connect/{key}">Connect</a>'
        )
        rows.append(f'<li><span>{labels.get(key, key)}</span> {badge}</li>')
    name = profile.name or "there"
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cash — Finish setup</title>
<style>
 body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:560px;margin:40px auto;padding:0 20px;color:#1a1a1a}}
 h1{{font-size:1.5rem}} ul{{list-style:none;padding:0}}
 li{{display:flex;justify-content:space-between;align-items:center;padding:14px 16px;border:1px solid #eee;border-radius:10px;margin:10px 0}}
 .btn{{background:#111;color:#fff;text-decoration:none;padding:8px 14px;border-radius:8px;font-size:.9rem}}
 .finish{{display:inline-block;margin-top:18px;background:#2563eb}}
 .note{{color:#888;font-size:.85rem;margin-top:24px}}
</style></head>
<body>
 <h1>Welcome {name}, let's finish setting up Cash</h1>
 <p>Connect the accounts you'd like me to help with. You can add the rest later.</p>
 <ul>{''.join(rows)}</ul>
 <form method="post" action="/onboard/{token}/complete">
   <button class="btn finish" type="submit">I'm done — activate Cash</button>
 </form>
 <p class="note">This link is private to you and expires automatically.</p>
</body></html>"""


@app.get("/onboard/{token}", response_class=HTMLResponse)
def onboard_page(token: str):
    payload = _onboard_payload_or_404(token)
    from services.onboarding import profiles as onboarding_profiles
    from services.tenancy import tenant_context

    with tenant_context(payload.get("tid") or "default"):
        profile = onboarding_profiles.get_or_create(payload["pid"])
    return HTMLResponse(_render_setup_page(token, profile))


@app.get("/onboard/{token}/connect/{integration}")
def onboard_connect(token: str, integration: str):
    """Mark an integration as connected, then return to the setup page.

    In production this is where the provider OAuth flow begins (Google consent
    screen, etc.) and the callback marks it connected with the per-customer
    token stored in the secret vault. See docs/architecture/cash-onboarding.md.
    """
    payload = _onboard_payload_or_404(token)
    from services.onboarding import profiles as onboarding_profiles
    from services.tenancy import tenant_context

    with tenant_context(payload.get("tid") or "default"):
        onboarding_profiles.mark_integration_connected(payload["pid"], integration)
    return RedirectResponse(url=f"/onboard/{token}", status_code=303)


@app.post("/onboard/{token}/complete", response_class=HTMLResponse)
def onboard_complete(token: str):
    payload = _onboard_payload_or_404(token)
    from services.onboarding import profiles as onboarding_profiles
    from services.tenancy import tenant_context

    with tenant_context(payload.get("tid") or "default"):
        onboarding_profiles.mark_active(payload["pid"])
    return HTMLResponse(
        "<!doctype html><html><body style='font-family:sans-serif;max-width:520px;"
        "margin:60px auto;text-align:center'><h1>You're all set!</h1>"
        "<p>Head back to your chat with Cash — I'm ready to help.</p></body></html>"
    )


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
