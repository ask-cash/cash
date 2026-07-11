"""
dashboard.py — FastAPI routes + HTML for the management dashboard (Phase 2, step 3).

Auth is a magic link (a signed token Cash sends in chat) exchanged for a signed
session cookie; everything is scoped to the session's person_id + tenant_id under
the existing tenant RLS. All data/auth logic lives in ``services.dashboard`` (no
framework imports there) so it's unit-testable; this module is just the web edge.
"""

from __future__ import annotations

import html
import logging
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from services.config import settings
from services import dashboard as svc
from services.tenancy import tenant_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _session(request: Request) -> Optional[dict]:
    return svc.session_from_token(request.cookies.get(svc.SESSION_COOKIE))


@router.get("/login")
def login(token: str):
    """Exchange a magic-link token for a session cookie."""
    payload = svc.session_from_token(token)
    if not payload:
        return HTMLResponse(
            "<h1>This link has expired</h1><p>Ask Cash for a fresh dashboard link.</p>",
            status_code=401,
        )
    session = svc.make_session_token(payload["pid"], payload.get("tid", "default"))
    resp = RedirectResponse(url="/dashboard", status_code=303)
    resp.set_cookie(
        svc.SESSION_COOKIE, session,
        max_age=svc.SESSION_TTL_HOURS * 3600,
        httponly=True, samesite="lax",
        secure=(settings.public_base_url or "").startswith("https"),
    )
    return resp


@router.get("/logout")
def logout():
    resp = RedirectResponse(url="/dashboard", status_code=303)
    resp.delete_cookie(svc.SESSION_COOKIE)
    return resp


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def overview(request: Request):
    s = _session(request)
    if not s:
        return HTMLResponse(_render_login_required(), status_code=401)
    return HTMLResponse(_render_overview(svc.overview(s["pid"], s.get("tid", "default"))))


@router.get("/connect/discord", response_class=HTMLResponse)
def connect_discord(request: Request):
    s = _session(request)
    if not s:
        return HTMLResponse(_render_login_required(), status_code=401)
    # Step 4 (next): user DMs this phrase to the Cash Discord bot; the connector
    # verifies it and calls services.identity.link_identities to fold their
    # Discord person into this session's person. Bot-side verify is the remaining wiring.
    phrase = svc.make_connect_phrase(s["pid"], s.get("tid", "default"))
    return HTMLResponse(_render_connect_discord(phrase))


@router.get("/integrations", response_class=HTMLResponse)
def integrations_view(request: Request):
    s = _session(request)
    if not s:
        return HTMLResponse(_render_login_required(), status_code=401)
    from services import integrations
    tid = s.get("tid", "default")
    with tenant_context(tid):
        rows = [
            {
                "id": p.id,
                "title": p.title,
                "available": p.available,
                "connected": integrations.is_connected(p.id),
                "unlocks": list(p.unlocks),
            }
            for p in integrations.all_providers()
        ]
    return HTMLResponse(_render_integrations(rows))


@router.get("/memory", response_class=HTMLResponse)
def memory_view(request: Request):
    s = _session(request)
    if not s:
        return HTMLResponse(_render_login_required(), status_code=401)
    from services.memory import build_memory_context
    tid = s.get("tid", "default")
    with tenant_context(tid):
        memory = build_memory_context(days=14)
    return HTMLResponse(_render_memory(memory))


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cash — Dashboard</title>
<style>
 body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:640px;margin:48px auto;padding:0 20px;color:#1a1a1a}}
 h1{{font-size:1.6rem}} h2{{font-size:1.05rem;margin-top:28px;color:#444}}
 .card{{border:1px solid #eee;border-radius:12px;padding:16px 18px;margin:12px 0;background:#fafafa}}
 .pill{{display:inline-block;background:#eef;border-radius:999px;padding:3px 10px;margin:3px;font-size:.85rem}}
 .btn{{display:inline-block;background:#2563eb;color:#fff;text-decoration:none;padding:10px 16px;border-radius:8px;margin-top:8px}}
 .muted{{color:#888;font-size:.85rem}} code{{background:#f0f0f0;padding:2px 6px;border-radius:6px}}
</style></head><body>{body}</body></html>"""


def _render_login_required() -> str:
    return _PAGE.format(body=(
        "<h1>Cash Dashboard</h1>"
        "<p>Open the dashboard link Cash sent you in chat to sign in.</p>"
    ))


def _render_overview(d: dict) -> str:
    admin_badge = " · <span class='pill'>admin</span>" if d.get("is_admin") else ""
    if d["platforms"]:
        plats = "".join(
            f"<span class='pill'>{html.escape(p['platform'])}: {html.escape(str(p['handle']))}</span>"
            for p in d["platforms"]
        )
    else:
        plats = "<span class='muted'>none yet</span>"
    summary = html.escape(d["summary"]) if d["summary"] else "<span class='muted'>nothing yet</span>"
    body = (
        f"<h1>Hi {html.escape(d['name'])}{admin_badge}</h1>"
        "<h2>Connected platforms</h2>"
        f"<div class='card'>{plats}</div>"
        "<a class='btn' href='/dashboard/connect/discord'>+ Connect Discord</a>"
        " <a class='btn' href='/dashboard/integrations'>All integrations</a>"
        "<h2>What Cash remembers</h2>"
        f"<div class='card'>{summary}<br><span class='muted'>"
        f"{d['conversation_count']} messages on record</span></div>"
        "<a class='btn' href='/dashboard/memory'>View memory</a>"
        "<p class='muted'><a href='/dashboard/logout'>Sign out</a></p>"
    )
    return _PAGE.format(body=body)


def _render_integrations(rows: list[dict]) -> str:
    items = []
    for r in rows:
        if not r["available"]:
            status = "<span class='muted'>coming soon</span>"
        elif r["connected"]:
            status = "<span class='pill'>✅ connected</span>"
        else:
            status = "<span class='pill'>not connected</span>"
        unlocks = "".join(f"<span class='pill'>{html.escape(u)}</span>" for u in r["unlocks"])
        if not unlocks:
            unlocks = "<span class='muted'>—</span>"
        items.append(
            f"<div class='card'><b>{html.escape(r['title'])}</b> — {status}<br>"
            f"<span class='muted'>unlocks:</span> {unlocks}</div>"
        )
    body = (
        "<h1>Integrations</h1>"
        "<p class='muted'>Connecting a provider unlocks its skills.</p>"
        + "".join(items)
        + "<p><a href='/dashboard'>← Back</a></p>"
    )
    return _PAGE.format(body=body)


def _render_memory(memory: str) -> str:
    shown = html.escape(memory) if memory else "<span class='muted'>nothing yet</span>"
    body = (
        "<h1>What Cash remembers</h1>"
        f"<div class='card' style='white-space:pre-wrap'>{shown}</div>"
        "<p><a href='/dashboard'>← Back</a></p>"
    )
    return _PAGE.format(body=body)


def _render_connect_discord(phrase: str) -> str:
    body = (
        "<h1>Connect Discord</h1>"
        "<p>To link your Discord so Cash shares one memory across platforms:</p>"
        "<ol><li>Open Discord and DM the Cash bot.</li>"
        "<li>Send it this exact message (copy all of it):</li></ol>"
        f"<div class='card'><code>/link {html.escape(phrase)}</code></div>"
        "<p>Cash will reply to confirm, and your accounts will share one memory.</p>"
        "<p class='muted'>This code expires in 1 hour.</p>"
        "<p><a href='/dashboard'>← Back</a></p>"
    )
    return _PAGE.format(body=body)
