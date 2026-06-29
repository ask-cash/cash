"""
telegram_poller.py — Long-polling Telegram for local / single-tenant runs.

An alternative to the webhook path (gateway receives POST /tg/{token} -> queue
-> worker). Instead of Telegram PUSHing updates to a public URL, this process
PULLs them with getUpdates. No PUBLIC_BASE_URL, no ngrok, no setWebhook — just
TELEGRAM_BOT_TOKEN from .env.

It mirrors the Discord connector's "from .env, default tenant" pattern so it
runs inside the same Docker stack against Postgres and uses the exact same
handler set (bot.app_factory.register_handlers, incl. onboarding). Scheduled
jobs (briefings, summary rollups) stay the cron role's responsibility; this
process only handles live messages.

Run:  python -m app telegram-poller
"""

from __future__ import annotations

import logging
import os

from telegram import Update
from telegram.ext import Application

import asyncio

from app.observability import configure_logging
from bot.app_factory import register_handlers
from services import oauth_server
from services.config import settings
from services.db import bootstrap
from services.tenancy import tenant_context

configure_logging()
logger = logging.getLogger(__name__)


def _owner_id() -> int:
    """The owner's Telegram user id for this tenant.

    Prefers the ``owner_telegram_id`` secret written at onboarding (DB-backed,
    per tenant); falls back to env for local single-tenant runs.
    """
    try:
        from services import secrets as secret_vault
        val = secret_vault.get_secret("owner_telegram_id", tenant_id=settings.default_tenant_id)
        if val and val.strip().isdigit():
            return int(val)
    except Exception:
        logger.debug("[telegram-poller] owner_telegram_id secret lookup failed; using env", exc_info=True)
    raw = os.getenv("YOUR_TELEGRAM_USER_ID") or os.getenv("TG_OWNER_ID") or "0"
    return int(raw) if raw.strip().isdigit() else 0


def _wire_oauth_server(app: Application) -> None:
    """Start the Google OAuth callback server so /connect_google works.

    Mirrors main.py: without this, create_auth_url raises "OAuth server not
    configured" even when OAUTH_REDIRECT_URI is set, because configure() was
    never called in this process.
    """
    redirect_uri = os.getenv("OAUTH_REDIRECT_URI", "").strip()
    if not redirect_uri:
        logger.warning("[telegram-poller] OAUTH_REDIRECT_URI unset — /connect_google disabled")
        return
    from bot.handlers.commands import on_google_connected

    on_google_connected._app = app  # type: ignore[attr-defined]
    oauth_server.configure(
        redirect_uri=redirect_uri,
        on_success=on_google_connected,
        loop=asyncio.get_running_loop(),
        creds_path=os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json"),
    )
    port = int(os.getenv("OAUTH_SERVER_PORT", "8401"))
    try:
        oauth_server.start_oauth_server(port)
        logger.info("[telegram-poller] OAuth callback server on :%d (redirect=%s)", port, redirect_uri)
    except Exception:
        logger.exception("[telegram-poller] could not start OAuth server on :%d", port)


async def _post_init(app: Application) -> None:
    # getUpdates returns 409 Conflict if a webhook is still registered, so clear
    # it. This is also what makes "switch to polling" take effect even if a
    # previous run set a webhook via the gateway.
    try:
        await app.bot.delete_webhook(drop_pending_updates=False)
        logger.info("[telegram-poller] cleared any existing webhook")
    except Exception:
        logger.exception("[telegram-poller] delete_webhook failed (continuing)")
    _wire_oauth_server(app)
    _reload_reminders(app)


def _reload_reminders(app: Application) -> None:
    """Re-schedule persisted reminders on boot so they survive restarts.

    Overdue reminders (their time passed while we were down) fire shortly after
    startup rather than being silently dropped.
    """
    import datetime as dt

    from services import reminders
    from services.tenancy import tenant_context
    from services.user_profile import now as _now
    from bot.handlers.messages import schedule_reminder_job

    try:
        with tenant_context(settings.default_tenant_id):
            pending = reminders.list_pending()
    except Exception:
        logger.exception("[telegram-poller] could not load reminders")
        return

    now = _now()
    rescheduled = 0
    for rec in pending:
        try:
            when = dt.datetime.fromisoformat(rec["when"])
            if when <= now:  # overdue — fire a few seconds from now
                rec = {**rec, "when": (now + dt.timedelta(seconds=5)).isoformat()}
            schedule_reminder_job(app.job_queue, rec)
            rescheduled += 1
        except Exception:
            logger.exception("[telegram-poller] could not reschedule reminder %s", rec.get("id"))
    if rescheduled:
        logger.info("[telegram-poller] re-scheduled %d reminder(s)", rescheduled)


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("❌ TELEGRAM_BOT_TOKEN not set — required for the poller")

    bootstrap()
    owner_id = _owner_id()
    tenant = settings.default_tenant_id

    app = Application.builder().token(token).post_init(_post_init).build()
    register_handlers(app, owner_id=owner_id)

    logger.info(
        "[telegram-poller] polling (tenant=%s, owner_id=%s, onboarding=%s)",
        tenant, owner_id, settings.onboarding_enabled,
    )
    # Set the tenant for the whole polling loop; handler tasks (and asyncio
    # to_thread calls, which copy the context) inherit it, so the data layer is
    # correctly scoped to the default tenant.
    with tenant_context(tenant):
        app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
