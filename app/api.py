"""
api.py — the JSON API the web client (client/) talks to.

Mounted under /api on the gateway. Everything is real and Postgres-backed:

  * Auth — email/password + Google OAuth via services.accounts (users, tenants,
    persons in the DB). A signed session cookie carries (person_id, tenant_id),
    the same one the magic-link dashboard uses, so every downstream service is
    tenant-scoped.
  * Connectors — the Feature 7 integration registry + TokenManager. Google
    Calendar runs a real OAuth flow; the resulting token is stored encrypted in
    the per-tenant secrets vault (tenant_secrets, Postgres).
  * Chat — routes to the owner brain + shared memory + the web action executor,
    so the browser has the same functionality as Telegram.

The router holds no framework logic beyond request/response glue; the substance
lives in services.* (unit-tested without FastAPI).
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from services import accounts
from services import dashboard as svc
from services import integrations
from services.config import settings
from services.tenancy import tenant_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["api"])

_CLIENT_BASE = os.getenv("CLIENT_BASE_URL", "").rstrip("/")


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def _session(request: Request):
    return svc.session_from_token(request.cookies.get(svc.SESSION_COOKIE))


def _is_https(request: Request) -> bool:
    # Honour the scheme the browser actually used (X-Forwarded-Proto behind
    # nginx), so the cookie is only marked Secure on real HTTPS — otherwise a
    # localhost/http session cookie would be silently dropped by the browser.
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    return (proto or request.url.scheme) == "https"


def _set_session_cookie(resp: Response, request: Request, person_id: str, tenant_id: str) -> None:
    token = svc.make_session_token(person_id, tenant_id)
    resp.set_cookie(
        svc.SESSION_COOKIE, token,
        max_age=svc.SESSION_TTL_HOURS * 3600,
        httponly=True, samesite="lax",
        secure=_is_https(request),
    )


def _account_view(account: dict) -> dict:
    with tenant_context(account["tenant_id"]):
        calendar_connected = integrations.is_connected("google_calendar")
    return {
        "id": account["person_id"],
        "email": account["email"],
        "firstName": account["first_name"],
        "lastName": account["last_name"],
        "role": account["role"],
        "platforms": account["platforms"],
        "onboarded": account["onboarded"],
        "calendarConnected": calendar_connected,
    }


def _current_account(request: Request):
    s = _session(request)
    if not s:
        return None
    return accounts.get_account_by_person(s["pid"])


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class SignUpBody(BaseModel):
    firstName: str = ""
    lastName: str = ""
    email: str
    password: str


class LoginBody(BaseModel):
    email: str
    password: str


class ProfileBody(BaseModel):
    firstName: str | None = None
    lastName: str | None = None
    role: str | None = None
    platforms: list[str] | None = None
    onboarded: bool | None = None


@router.post("/auth/signup")
def signup(body: SignUpBody, request: Request):
    if len(body.password) < 6:
        return JSONResponse({"error": "Password must be at least 6 characters."}, status_code=400)
    try:
        account = accounts.create_account(body.email, body.password, body.firstName, body.lastName)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    resp = JSONResponse({"user": _account_view(account)})
    _set_session_cookie(resp, request, account["person_id"], account["tenant_id"])
    return resp


@router.post("/auth/login")
def login(body: LoginBody, request: Request):
    account = accounts.verify_login(body.email, body.password)
    if not account:
        return JSONResponse({"error": "Invalid email or password."}, status_code=401)
    resp = JSONResponse({"user": _account_view(account)})
    _set_session_cookie(resp, request, account["person_id"], account["tenant_id"])
    return resp


@router.post("/auth/logout")
def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(svc.SESSION_COOKIE)
    return resp


@router.get("/auth/me")
def me(request: Request):
    account = _current_account(request)
    if not account:
        return JSONResponse({"user": None}, status_code=401)
    return {"user": _account_view(account)}


@router.patch("/auth/profile")
def update_profile(body: ProfileBody, request: Request):
    account = _current_account(request)
    if not account:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    patch = {
        "first_name": body.firstName,
        "last_name": body.lastName,
        "role": body.role,
        "platforms": body.platforms,
        "onboarded": body.onboarded,
    }
    patch = {k: v for k, v in patch.items() if v is not None}
    updated = accounts.update_profile(account["email"], **patch)
    return {"user": _account_view(updated)}


# ---------------------------------------------------------------------------
# Google sign-in (OAuth) — reuses the Google OAuth client for identity
# ---------------------------------------------------------------------------

_AUTH_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]


def _auth_callback_uri() -> str:
    base = (settings.public_base_url or "").rstrip("/")
    return f"{base}/api/auth/google/callback"


@router.get("/auth/google/start")
def google_auth_start():
    from google_auth_oauthlib.flow import Flow
    creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
    # A signed nonce as state guards against CSRF on the callback.
    state = svc.make_session_token("google-auth", "auth")
    try:
        flow = Flow.from_client_secrets_file(creds_path, scopes=_AUTH_SCOPES, state=state)
        flow.redirect_uri = _auth_callback_uri()
        auth_url, _ = flow.authorization_url(access_type="online", include_granted_scopes="true", prompt="select_account")
    except Exception as e:
        logger.exception("google_auth_start failed")
        return JSONResponse({"error": f"Google sign-in not configured: {e}"}, status_code=500)
    return RedirectResponse(url=auth_url, status_code=307)


@router.get("/auth/google/callback")
def google_auth_callback(request: Request):
    import requests as _rq
    from google_auth_oauthlib.flow import Flow

    state = request.query_params.get("state", "")
    code = request.query_params.get("code", "")
    if not svc.session_from_token(state) or not code:
        return RedirectResponse(url=f"{_CLIENT_BASE}/signin?error=google", status_code=303)
    try:
        creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
        flow = Flow.from_client_secrets_file(creds_path, scopes=_AUTH_SCOPES, state=state)
        flow.redirect_uri = _auth_callback_uri()
        flow.fetch_token(code=code)
        info = _rq.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {flow.credentials.token}"},
            timeout=15,
        ).json()
        email = info.get("email")
        if not email:
            raise ValueError("no email in Google profile")
        account = accounts.get_or_create_oauth_account(
            email, info.get("given_name", ""), info.get("family_name", ""))
    except Exception:
        logger.exception("google_auth_callback failed")
        return RedirectResponse(url=f"{_CLIENT_BASE}/signin?error=google", status_code=303)

    dest = "/app" if account["onboarded"] else "/onboarding"
    resp = RedirectResponse(url=f"{_CLIENT_BASE}{dest}", status_code=303)
    _set_session_cookie(resp, request, account["person_id"], account["tenant_id"])
    return resp


# ---------------------------------------------------------------------------
# Connectors
# ---------------------------------------------------------------------------

@router.get("/connectors")
def connectors(request: Request):
    s = _session(request)
    if not s:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return {"connectors": svc.connectors_status(s.get("tid", "default"))}


@router.post("/connectors/{provider}/disconnect")
def disconnect(provider: str, request: Request):
    s = _session(request)
    if not s:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return {"disconnected": svc.disconnect_provider(s.get("tid", "default"), provider)}


# ---------------------------------------------------------------------------
# Google Calendar OAuth (real; token stored in the per-tenant vault)
# ---------------------------------------------------------------------------

def _google_flow(redirect_uri: str, state: str | None = None):
    from google_auth_oauthlib.flow import Flow
    p = integrations.registry.get("google_calendar")
    creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
    flow = Flow.from_client_secrets_file(creds_path, scopes=list(p.scopes), state=state)
    flow.redirect_uri = redirect_uri
    return flow


def _callback_uri() -> str:
    base = (settings.public_base_url or "").rstrip("/")
    return f"{base}/api/connect/google/callback"


@router.get("/connect/google/start")
def google_start(request: Request):
    s = _session(request)
    if not s:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    # The signed session token IS the OAuth state: stateless + multi-process safe,
    # and the callback recovers the tenant from it without shared memory.
    state = svc.make_session_token(s["pid"], s.get("tid", "default"))
    try:
        flow = _google_flow(_callback_uri(), state=state)
        auth_url, _ = flow.authorization_url(
            access_type="offline", include_granted_scopes="true", prompt="consent",
        )
    except Exception as e:
        logger.exception("google_start failed")
        return JSONResponse({"error": f"OAuth not configured: {e}"}, status_code=500)
    return RedirectResponse(url=auth_url, status_code=307)


@router.get("/connect/google/callback")
def google_callback(request: Request):
    state = request.query_params.get("state", "")
    code = request.query_params.get("code", "")
    payload = svc.session_from_token(state)
    if not payload or not code:
        return RedirectResponse(url=f"{_CLIENT_BASE}/app/integrations?error=oauth", status_code=303)
    try:
        flow = _google_flow(_callback_uri(), state=state)
        flow.fetch_token(code=code)
        creds_json = flow.credentials.to_json()
        with tenant_context(payload.get("tid", "default")):
            integrations.store_token("google_calendar", creds_json)
    except Exception:
        logger.exception("google_callback failed")
        return RedirectResponse(url=f"{_CLIENT_BASE}/app/integrations?error=oauth", status_code=303)
    return RedirectResponse(url=f"{_CLIENT_BASE}/app/integrations?connected=google-calendar", status_code=303)


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatBody(BaseModel):
    message: str


@router.post("/chat")
async def chat(body: ChatBody, request: Request):
    s = _session(request)
    if not s:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    message = (body.message or "").strip()
    if not message:
        return {"reply": ""}
    import asyncio
    out = await asyncio.to_thread(svc.chat_reply, s["pid"], s.get("tid", "default"), message)
    return out
