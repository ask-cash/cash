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
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from services.config import settings
from services import dashboard as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _session(request: Request) -> Optional[dict]:
    return svc.session_from_token(request.cookies.get(svc.SESSION_COOKIE))


def _session_cookie(request: Request) -> str:
    return request.cookies.get(svc.SESSION_COOKIE) or ""


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


@router.get("/integrations")
def integrations_view():
    # Superseded by /connectors (kept as a stable alias).
    return RedirectResponse(url="/dashboard/connectors", status_code=307)


@router.get("/memory", response_class=HTMLResponse)
def memory_view(request: Request):
    s = _session(request)
    if not s:
        return HTMLResponse(_render_login_required(), status_code=401)
    tid = s.get("tid", "default")
    items = svc.memory_items(tid)
    csrf = svc.csrf_token(_session_cookie(request))
    return HTMLResponse(_render_memory(items, csrf))


@router.post("/memory/redact")
async def memory_redact(request: Request):
    s = _session(request)
    if not s:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    body = await request.json()
    if not svc.verify_csrf(_session_cookie(request), body.get("csrf", "")):
        return JSONResponse({"error": "bad csrf"}, status_code=403)
    removed = svc.redact_fact(s.get("tid", "default"), body.get("fingerprint", ""))
    return JSONResponse({"removed": removed})


# --- Connectors ------------------------------------------------------------

@router.get("/connectors", response_class=HTMLResponse)
def connectors(request: Request):
    s = _session(request)
    if not s:
        return HTMLResponse(_render_login_required(), status_code=401)
    rows = svc.connectors_status(s.get("tid", "default"))
    csrf = svc.csrf_token(_session_cookie(request))
    return HTMLResponse(_render_connectors(rows, csrf))


@router.get("/connect/{provider}", response_class=HTMLResponse)
def connect_provider(provider: str, request: Request):
    s = _session(request)
    if not s:
        return HTMLResponse(_render_login_required(), status_code=401)
    if provider == "discord":
        return connect_discord(request)
    from services.integrations import registry
    p = registry.get(provider)
    if not p or not p.available:
        return HTMLResponse(_render_connect_hint(provider, "This connector isn't available yet."))
    return HTMLResponse(_render_connect_hint(p.title, p.connect_hint))


@router.post("/disconnect/{provider}")
async def disconnect_provider(provider: str, request: Request):
    s = _session(request)
    if not s:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    body = await request.json()
    if not svc.verify_csrf(_session_cookie(request), body.get("csrf", "")):
        return JSONResponse({"error": "bad csrf"}, status_code=403)
    cleared = svc.disconnect_provider(s.get("tid", "default"), provider)
    return JSONResponse({"disconnected": cleared})


# --- Preferred proactive channel ------------------------------------------

@router.get("/notify", response_class=HTMLResponse)
def notify_view(request: Request):
    s = _session(request)
    if not s:
        return HTMLResponse(_render_login_required(), status_code=401)
    current = svc.get_notify_channel(s.get("tid", "default"))
    csrf = svc.csrf_token(_session_cookie(request))
    return HTMLResponse(_render_notify(current, csrf))


@router.post("/notify")
async def notify_set(request: Request):
    s = _session(request)
    if not s:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    body = await request.json()
    if not svc.verify_csrf(_session_cookie(request), body.get("csrf", "")):
        return JSONResponse({"error": "bad csrf"}, status_code=403)
    chosen = svc.set_notify_channel(s.get("tid", "default"), body.get("channel", "telegram"))
    return JSONResponse({"channel": chosen})


# --- Web chat --------------------------------------------------------------

@router.get("/chat", response_class=HTMLResponse)
def chat_view(request: Request):
    s = _session(request)
    if not s:
        return HTMLResponse(_render_login_required(), status_code=401)
    csrf = svc.csrf_token(_session_cookie(request))
    return HTMLResponse(_render_chat(csrf))


@router.post("/chat")
async def chat_send(request: Request):
    s = _session(request)
    if not s:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    body = await request.json()
    if not svc.verify_csrf(_session_cookie(request), body.get("csrf", "")):
        return JSONResponse({"error": "bad csrf"}, status_code=403)
    message = (body.get("message") or "").strip()
    if not message:
        return JSONResponse({"reply": ""})
    import asyncio
    out = await asyncio.to_thread(
        svc.chat_reply, s["pid"], s.get("tid", "default"), message
    )
    return JSONResponse(out)


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
        "<a class='btn' href='/dashboard/chat'>💬 Chat with Cash</a>"
        "<h2>Connected platforms</h2>"
        f"<div class='card'>{plats}</div>"
        "<a class='btn' href='/dashboard/connectors'>Manage connectors</a>"
        " <a class='btn' href='/dashboard/notify'>Notifications</a>"
        "<h2>What Cash remembers</h2>"
        f"<div class='card'>{summary}<br><span class='muted'>"
        f"{d['conversation_count']} messages on record</span></div>"
        "<a class='btn' href='/dashboard/memory'>View memory</a>"
        "<p class='muted'><a href='/dashboard/logout'>Sign out</a></p>"
    )
    return _PAGE.format(body=body)


def _render_connectors(rows: list[dict], csrf: str) -> str:
    items = []
    for r in rows:
        pid = html.escape(r["id"])
        if not r["available"]:
            status = "<span class='muted'>coming soon</span>"
            action = ""
        elif r["connected"]:
            status = "<span class='pill'>✅ connected</span>"
            action = f"<button onclick=\"disc('{pid}')\">Disconnect</button>"
        else:
            status = "<span class='pill'>not connected</span>"
            action = f"<a class='btn' href='/dashboard/connect/{pid}'>Connect</a>"
        unlocks = "".join(f"<span class='pill'>{html.escape(u)}</span>" for u in r["unlocks"]) \
            or "<span class='muted'>—</span>"
        items.append(
            f"<div class='card'><b>{html.escape(r['title'])}</b> — {status}<br>"
            f"<span class='muted'>unlocks:</span> {unlocks}<br>{action}</div>"
        )
    script = (
        "<script>async function disc(p){"
        "await fetch('/dashboard/disconnect/'+p,{method:'POST',headers:{'Content-Type':'application/json'},"
        f"body:JSON.stringify({{csrf:'{html.escape(csrf)}'}})}});location.reload();}}</script>"
    )
    body = (
        "<h1>Connectors</h1>"
        "<p class='muted'>Connecting a provider unlocks its skills.</p>"
        + "".join(items)
        + "<p><a href='/dashboard'>← Back</a></p>" + script
    )
    return _PAGE.format(body=body)


def _render_connect_hint(title: str, hint: str) -> str:
    body = (
        f"<h1>Connect {html.escape(title)}</h1>"
        f"<div class='card'>{html.escape(hint or 'Follow the steps Cash gives you in chat.')}</div>"
        "<p><a href='/dashboard/connectors'>← Back to connectors</a></p>"
    )
    return _PAGE.format(body=body)


def _render_notify(current: str, csrf: str) -> str:
    options = ["telegram", "discord", "slack"]
    buttons = "".join(
        f"<button onclick=\"pick('{o}')\">{o}{' ✓' if o == current else ''}</button> "
        for o in options
    )
    script = (
        "<script>async function pick(c){"
        "await fetch('/dashboard/notify',{method:'POST',headers:{'Content-Type':'application/json'},"
        f"body:JSON.stringify({{channel:c,csrf:'{html.escape(csrf)}'}})}});location.reload();}}</script>"
    )
    body = (
        "<h1>Proactive notifications</h1>"
        f"<p>Where should Cash reach you first? Currently: <b>{html.escape(current)}</b></p>"
        f"<div class='card'>{buttons}</div>"
        "<p><a href='/dashboard'>← Back</a></p>" + script
    )
    return _PAGE.format(body=body)


def _render_memory(items: dict, csrf: str) -> str:
    facts = items.get("facts", [])
    decisions = items.get("decisions", [])
    fact_html = []
    for f in facts:
        fp = html.escape(f.get("fingerprint", ""))
        fact_html.append(
            f"<div class='card'>{html.escape(f.get('fact', ''))}<br>"
            f"<button onclick=\"forget('{fp}')\">Forget</button></div>"
        )
    facts_block = "".join(fact_html) or "<span class='muted'>no facts yet</span>"
    dec_block = "".join(
        f"<div class='card'>{html.escape(d.get('decision', ''))} "
        f"<span class='muted'>({html.escape(str(d.get('scope', '')))})</span></div>"
        for d in decisions
    ) or "<span class='muted'>none</span>"
    script = (
        "<script>async function forget(fp){"
        "await fetch('/dashboard/memory/redact',{method:'POST',headers:{'Content-Type':'application/json'},"
        f"body:JSON.stringify({{fingerprint:fp,csrf:'{html.escape(csrf)}'}})}});location.reload();}}</script>"
    )
    body = (
        "<h1>What Cash remembers</h1>"
        "<h2>Facts</h2>" + facts_block
        + "<h2>Decisions</h2>" + dec_block
        + "<p><a href='/dashboard'>← Back</a></p>" + script
    )
    return _PAGE.format(body=body)


def _render_chat(csrf: str) -> str:
    body = (
        "<h1>Chat with Cash 🐈‍⬛</h1>"
        "<div id='log' class='card' style='min-height:240px;white-space:pre-wrap'></div>"
        "<div style='display:flex;gap:8px;margin-top:10px'>"
        "<input id='msg' style='flex:1;padding:10px;border:1px solid #ddd;border-radius:8px' "
        "placeholder='Say something to Cash…' onkeydown='if(event.key===\"Enter\")send()'>"
        "<button class='btn' onclick='send()'>Send</button></div>"
        "<p class='muted'><a href='/dashboard'>← Back</a></p>"
        "<script>"
        "const log=document.getElementById('log'),inp=document.getElementById('msg');"
        "function add(who,t){log.innerHTML+= '\\n'+who+': '+t;}"
        "async function send(){const m=inp.value.trim();if(!m)return;inp.value='';"
        "add('You',m);add('Cash','…');"
        "const r=await fetch('/dashboard/chat',{method:'POST',headers:{'Content-Type':'application/json'},"
        f"body:JSON.stringify({{message:m,csrf:'{html.escape(csrf)}'}})}});"
        "const d=await r.json();"
        "log.innerHTML=log.innerHTML.replace(/…$/,'')+ (d.reply||'(no reply)');}"
        "</script>"
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
