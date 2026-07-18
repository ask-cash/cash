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

import asyncio
import logging
import os
import tempfile
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, File, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from services import accounts
from services import attachments
from services import chat_policy
from services import dashboard as svc
from services import integrations
from services import rate_limits
from services import storage
from services import transcription
from services.chat_runtime import ConversationBusyError
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
        "plan": account.get("plan", "free"),
        "calendarConnected": calendar_connected,
    }


def _current_account(request: Request):
    s = _session(request)
    if not s:
        return None
    return accounts.get_account_by_person(s["pid"])


def _require_same_origin(request: Request) -> JSONResponse | None:
    """Reject credentialed browser mutations originating on another site."""
    fetch_site = request.headers.get("sec-fetch-site", "").lower()
    if fetch_site == "cross-site":
        return JSONResponse({"error": "cross-site request rejected"}, status_code=403)
    origin = request.headers.get("origin")
    if not origin:
        return None
    allowed = {_CLIENT_BASE} if _CLIENT_BASE else set()
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    allowed.add(f"{proto or request.url.scheme}://{request.headers.get('host', request.url.netloc)}")
    normalized = f"{urlparse(origin).scheme}://{urlparse(origin).netloc}"
    if normalized not in allowed:
        return JSONResponse({"error": "origin not allowed"}, status_code=403)
    return None


def _rate_limit_response(request: Request, tenant_id: str, category: str, limit: int):
    try:
        rate_limits.check(
            f"{category}:tenant:{tenant_id}",
            limit=limit,
            window_seconds=60,
        )
    except rate_limits.RateLimitExceeded as exc:
        return JSONResponse(
            {"error": str(exc), "code": "rate_limited"},
            status_code=429,
            headers={"Retry-After": str(exc.retry_after)},
        )
    except rate_limits.RateLimitUnavailable as exc:
        return JSONResponse(
            {"error": str(exc), "code": "rate_limit_unavailable"},
            status_code=503,
        )
    return None


def _service_error(exc: Exception) -> JSONResponse:
    if isinstance(exc, (chat_policy.ChatPolicyError, attachments.AttachmentError)):
        return JSONResponse(
            {"error": str(exc), "code": exc.code},
            status_code=exc.status_code,
        )
    if isinstance(exc, ConversationBusyError):
        return JSONResponse(
            {"error": str(exc), "code": "conversation_busy"},
            status_code=409,
        )
    if isinstance(exc, transcription.TranscriptionError):
        return JSONResponse(
            {"error": str(exc), "code": exc.code},
            status_code=exc.status_code,
        )
    if isinstance(exc, rate_limits.ConcurrencyLimitExceeded):
        return JSONResponse(
            {"error": str(exc), "code": "provider_at_capacity"},
            status_code=429,
            headers={"Retry-After": "2"},
        )
    if isinstance(exc, rate_limits.RateLimitUnavailable):
        return JSONResponse(
            {"error": str(exc), "code": "capacity_unavailable"},
            status_code=503,
        )
    logger.exception("dashboard service request failed")
    return JSONResponse(
        {"error": "Cash could not complete that request right now.", "code": "service_unavailable"},
        status_code=502,
    )


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
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    role: Optional[str] = None
    platforms: Optional[list[str]] = None
    onboarded: Optional[bool] = None


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


def _new_google_flow(
    scopes: list[str],
    redirect_uri: str,
    *,
    state: str | None = None,
):
    """Build a Google OAuth flow from production secrets or the local JSON file."""
    from google_auth_oauthlib.flow import Flow

    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
    if bool(client_id) != bool(client_secret):
        raise RuntimeError(
            "GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET must be set together"
        )
    if client_id:
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [redirect_uri],
                }
            },
            scopes=scopes,
            state=state,
        )
    else:
        creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
        flow = Flow.from_client_secrets_file(
            creds_path,
            scopes=scopes,
            state=state,
        )
    flow.redirect_uri = redirect_uri
    return flow


@router.get("/auth/google/start")
def google_auth_start():
    # A signed nonce as state guards against CSRF on the callback.
    state = svc.make_session_token("google-auth", "auth")
    try:
        flow = _new_google_flow(
            _AUTH_SCOPES,
            _auth_callback_uri(),
            state=state,
        )
        auth_url, _ = flow.authorization_url(access_type="online", include_granted_scopes="true", prompt="select_account")
    except Exception:
        logger.exception("google_auth_start failed")
        return JSONResponse(
            {"error": "Google sign-in is not configured for this deployment."},
            status_code=503,
        )
    return RedirectResponse(url=auth_url, status_code=307)


@router.get("/auth/google/callback")
def google_auth_callback(request: Request):
    import requests as _rq

    state = request.query_params.get("state", "")
    code = request.query_params.get("code", "")
    if not svc.session_from_token(state) or not code:
        return RedirectResponse(url=f"{_CLIENT_BASE}/signin?error=google", status_code=303)
    try:
        flow = _new_google_flow(
            _AUTH_SCOPES,
            _auth_callback_uri(),
            state=state,
        )
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
    p = integrations.registry.get("google_calendar")
    return _new_google_flow(list(p.scopes), redirect_uri, state=state)


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
            integrations.mark_connected("google_calendar")
    except Exception:
        logger.exception("google_callback failed")
        return RedirectResponse(url=f"{_CLIENT_BASE}/app/integrations?error=oauth", status_code=303)
    return RedirectResponse(url=f"{_CLIENT_BASE}/app/integrations?connected=google-calendar", status_code=303)


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatBody(BaseModel):
    # Keep JSON chat requests bounded independently from the larger multipart
    # body allowance needed by attachment uploads.
    message: str = Field(default="", max_length=1_000_000)
    modelId: Optional[str] = Field(default=None, max_length=128)
    attachmentIds: list[str] = Field(default_factory=list, max_length=20)
    clientRequestId: Optional[str] = Field(default=None, max_length=128)


@router.get("/chat/capabilities")
def chat_capabilities(request: Request):
    account = _current_account(request)
    if not account:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return chat_policy.capabilities(account.get("plan", "free"))


@router.post("/chat")
async def chat(body: ChatBody, request: Request):
    s = _session(request)
    if not s:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    if rejected := _require_same_origin(request):
        return rejected
    if settings.redis_url:
        return JSONResponse(
            {
                "error": (
                    "This legacy chat endpoint is disabled in distributed mode. "
                    "Create a conversation and send the message there."
                ),
                "code": "legacy_chat_disabled",
            },
            status_code=410,
        )
    account = accounts.get_account_by_person(s["pid"])
    plan = (account or {}).get("plan", "free")
    if limited := _rate_limit_response(
        request,
        s.get("tid", "default"),
        "chat",
        int(os.getenv("CHAT_REQUESTS_PER_MINUTE", "12")),
    ):
        return limited
    message = (body.message or "").strip()
    if not message:
        return {"reply": ""}
    try:
        model = chat_policy.require_model(plan, body.modelId).id
        return await asyncio.to_thread(
            svc.chat_reply,
            s["pid"],
            s.get("tid", "default"),
            message,
            model=model,
        )
    except Exception as exc:
        return _service_error(exc)


# ---------------------------------------------------------------------------
# Conversations (persistent chat threads, addressed by id)
# ---------------------------------------------------------------------------

class ConversationPatchBody(BaseModel):
    title: Optional[str] = Field(default=None, max_length=512)
    modelId: Optional[str] = Field(default=None, max_length=128)


def _in_tenant(request: Request, fn, *args):
    """Run a conversations call under the session's tenant context, in a thread."""
    import asyncio
    from services.tenancy import tenant_context

    s = _session(request)
    tid = s.get("tid", "default")

    def _run():
        with tenant_context(tid):
            return fn(*args)
    return asyncio.to_thread(_run)


@router.get("/conversations")
async def list_conversations(request: Request):
    if not _session(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    from services import conversations
    return {"conversations": await _in_tenant(request, conversations.list_conversations)}


@router.post("/conversations")
async def create_conversation(request: Request):
    s = _session(request)
    if not s:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    if rejected := _require_same_origin(request):
        return rejected
    from services import conversations
    account = accounts.get_account_by_person(s["pid"])
    model_id = chat_policy.default_model_id((account or {}).get("plan", "free"))
    return {
        "conversation": await _in_tenant(
            request,
            conversations.create_conversation,
            "",
            model_id,
        )
    }


@router.get("/conversations/{cid}/messages")
async def conversation_messages(cid: str, request: Request):
    s = _session(request)
    if not s:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    from services import conversations
    conv = await _in_tenant(request, conversations.get_conversation, cid)
    if conv is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    account = accounts.get_account_by_person(s["pid"])
    plan = (account or {}).get("plan", "free")
    model_id = conv.get("modelId") or chat_policy.default_model_id(plan)
    try:
        chat_policy.require_model(plan, model_id)
    except chat_policy.ChatPolicyError:
        model_id = chat_policy.default_model_id(plan)
        await _in_tenant(request, conversations.set_conversation_model, cid, model_id)
        conv["modelId"] = model_id
    messages = await _in_tenant(request, conversations.get_messages, cid)
    context = await _in_tenant(
        request,
        conversations.conversation_context,
        cid,
        plan,
        model_id,
    )
    return {"conversation": conv, "messages": messages, "context": context}


@router.post("/conversations/{cid}/messages")
async def send_conversation_message(cid: str, body: ChatBody, request: Request):
    s = _session(request)
    if not s:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    if rejected := _require_same_origin(request):
        return rejected
    if limited := _rate_limit_response(
        request,
        s.get("tid", "default"),
        "chat",
        int(os.getenv("CHAT_REQUESTS_PER_MINUTE", "12")),
    ):
        return limited
    message = (body.message or "").strip()
    if not message and not body.attachmentIds:
        return JSONResponse({"error": "Write a message or attach a file."}, status_code=400)
    from services import conversations
    account = accounts.get_account_by_person(s["pid"])
    plan = (account or {}).get("plan", "free")
    try:
        if settings.redis_url:
            prepared = await asyncio.to_thread(
                conversations.prepare_job,
                s["pid"],
                s.get("tid", "default"),
                cid,
                message,
                plan=plan,
                model_id=body.modelId,
                attachment_ids=body.attachmentIds,
                client_request_id=body.clientRequestId,
            )
            if prepared.get("status") == "complete" and prepared.get("result"):
                return prepared["result"]
            if prepared.get("status") == "failed":
                failure = prepared.get("error") or {}
                return JSONResponse(
                    {
                        "error": failure.get("message")
                        or "This message could not be processed.",
                        "code": failure.get("code") or "processing_failed",
                    },
                    status_code=502,
                )
            try:
                from services import queue

                await asyncio.to_thread(
                    queue.enqueue,
                    queue.CHAT_MESSAGE,
                    s.get("tid", "default"),
                    {"job_id": prepared["id"]},
                    idempotency_key=f"chat:{s.get('tid', 'default')}:{prepared['id']}",
                )
                await _in_tenant(
                    request,
                    conversations.mark_outbox_delivered,
                    prepared["id"],
                )
                queue_delayed = False
            except Exception:
                # The user turn and an outbox record committed atomically. Never
                # delete them after an ambiguous Redis result: a worker reconciler
                # will safely publish the idempotent job.
                logger.exception("chat enqueue deferred to transactional outbox")
                queue_delayed = True
            return JSONResponse(
                {
                    "jobId": prepared["id"],
                    "status": prepared["status"],
                    "userMessage": prepared.get("userMessage"),
                    "context": prepared.get("context"),
                    "modelId": prepared["modelId"],
                    "queueDelayed": queue_delayed,
                },
                status_code=202,
            )

        out = await asyncio.to_thread(
            conversations.send,
            s["pid"],
            s.get("tid", "default"),
            cid,
            message,
            plan=plan,
            model_id=body.modelId,
            attachment_ids=body.attachmentIds,
            client_request_id=body.clientRequestId,
        )
    except Exception as exc:
        return _service_error(exc)
    return out


@router.get("/chat/jobs/{job_id}")
async def chat_job(job_id: str, request: Request):
    if not _session(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    from services import conversations

    job = await _in_tenant(request, conversations.get_job, job_id)
    if job is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    if job["status"] == "complete":
        return {"status": "complete", "result": job["result"]}
    if job["status"] == "failed":
        return JSONResponse(
            {
                "error": (job.get("error") or {}).get("message")
                or "Cash could not complete this message.",
                "code": (job.get("error") or {}).get("code") or "processing_failed",
                "status": "failed",
            },
            status_code=502,
        )
    return {
        "status": job["status"],
        "jobId": job["id"],
        "attempts": job["attempts"],
    }


@router.patch("/conversations/{cid}")
async def update_conversation(cid: str, body: ConversationPatchBody, request: Request):
    s = _session(request)
    if not s:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    if rejected := _require_same_origin(request):
        return rejected
    from services import conversations
    conv = await _in_tenant(request, conversations.get_conversation, cid)
    if conv is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    try:
        if body.modelId is not None:
            account = accounts.get_account_by_person(s["pid"])
            model = chat_policy.require_model(
                (account or {}).get("plan", "free"),
                body.modelId,
            )
            await _in_tenant(
                request,
                conversations.set_conversation_model,
                cid,
                model.id,
            )
        if body.title is not None:
            await _in_tenant(
                request,
                conversations.rename_conversation,
                cid,
                body.title,
            )
    except Exception as exc:
        return _service_error(exc)
    updated = await _in_tenant(request, conversations.get_conversation, cid)
    return {"ok": True, "conversation": updated}


@router.delete("/conversations/{cid}")
async def delete_conversation(cid: str, request: Request):
    if not _session(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    if rejected := _require_same_origin(request):
        return rejected
    from services import conversations
    try:
        deleted = await _in_tenant(
            request,
            conversations.delete_conversation,
            cid,
        )
    except Exception as exc:
        return _service_error(exc)
    return {"deleted": deleted}


# ---------------------------------------------------------------------------
# Dashboard attachments + voice transcription
# ---------------------------------------------------------------------------

async def _spool_upload(upload: UploadFile, max_bytes: int) -> tuple[str, int]:
    suffix = os.path.splitext(upload.filename or "")[1][:12]
    fd, path = tempfile.mkstemp(prefix="cash-upload-", suffix=suffix)
    total = 0
    try:
        with os.fdopen(fd, "wb") as target:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise attachments.AttachmentError(
                        "That file is larger than your current upload limit.",
                        code="file_too_large",
                        status_code=413,
                    )
                target.write(chunk)
        return path, total
    except Exception:
        try:
            os.remove(path)
        except OSError:
            pass
        raise
    finally:
        await upload.close()


@router.post("/conversations/{cid}/attachments")
async def upload_conversation_attachments(
    cid: str,
    request: Request,
    files: list[UploadFile] = File(...),
):
    s = _session(request)
    if not s:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    if rejected := _require_same_origin(request):
        return rejected
    if limited := _rate_limit_response(
        request,
        s.get("tid", "default"),
        "upload",
        int(os.getenv("UPLOAD_REQUESTS_PER_MINUTE", "20")),
    ):
        return limited
    account = accounts.get_account_by_person(s["pid"])
    plan = (account or {}).get("plan", "free")
    if not files:
        return JSONResponse({"error": "No files were selected."}, status_code=400)
    if len(files) > attachments.max_files_per_message():
        return JSONResponse(
            {"error": f"Attach up to {attachments.max_files_per_message()} files per message."},
            status_code=400,
        )

    from services.tenancy import tenant_context

    created: list[dict] = []
    paths: list[str] = []
    try:
        for upload in files:
            path, _ = await _spool_upload(upload, attachments.max_file_bytes(plan))
            paths.append(path)

            def _store_and_process() -> dict:
                with tenant_context(s.get("tid", "default")):
                    inspected_mime, _, _ = attachments.inspect_path(
                        path,
                        filename=upload.filename or "upload",
                        declared_mime=upload.content_type or "",
                        plan=plan,
                    )
                    if attachments.is_audio_or_video(inspected_mime):
                        # Validate actual container duration before storing or
                        # spending any transcription provider capacity.
                        transcription.validate_media_duration(path)
                    record = attachments.create_from_path(
                        cid,
                        path,
                        original_name=upload.filename or "upload",
                        declared_mime=upload.content_type or "",
                        plan=plan,
                    )
                    if attachments.is_audio_or_video(record["mimeType"]):
                        if settings.redis_url:
                            try:
                                from services import queue

                                queue.enqueue(
                                    queue.MEDIA_TRANSCRIPTION,
                                    s.get("tid", "default"),
                                    {"attachment_id": record["id"]},
                                    idempotency_key=(
                                        f"media:{s.get('tid', 'default')}:{record['id']}"
                                    ),
                                )
                                attachments.mark_transcription_enqueued(
                                    record["id"]
                                )
                            except Exception:
                                # The processing row is itself the durable
                                # recovery source. Worker index zero republishes
                                # it when Redis is healthy again.
                                logger.exception(
                                    "media enqueue deferred for attachment %s",
                                    record["id"],
                                )
                        else:
                            try:
                                transcript = transcription.transcribe_path(
                                    path,
                                    filename=record["name"],
                                    mime_type=record["mimeType"],
                                )
                                record = attachments.set_transcript(
                                    record["id"],
                                    transcript,
                                )
                                attachments.mark_transcription_enqueued(
                                    record["id"]
                                )
                            except Exception:
                                attachments.delete_attachment(record["id"])
                                raise
                    public = attachments.get_attachment(record["id"])
                    return public or record

            created.append(await asyncio.to_thread(_store_and_process))
    except Exception as exc:
        with tenant_context(s.get("tid", "default")):
            for record in created:
                try:
                    attachments.delete_attachment(record["id"])
                except Exception:
                    logger.warning("failed to roll back attachment %s", record.get("id"))
        return _service_error(exc)
    finally:
        for path in paths:
            try:
                os.remove(path)
            except OSError:
                pass
    return {"attachments": created}


@router.get("/attachments/{attachment_id}/status")
async def attachment_status(attachment_id: str, request: Request):
    if not _session(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    record = await _in_tenant(
        request,
        attachments.get_attachment,
        attachment_id,
    )
    if record is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return {"attachment": record}


@router.delete("/attachments/{attachment_id}")
async def delete_attachment(attachment_id: str, request: Request):
    s = _session(request)
    if not s:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    if rejected := _require_same_origin(request):
        return rejected
    try:
        deleted = await _in_tenant(
            request,
            attachments.delete_attachment,
            attachment_id,
        )
    except Exception as exc:
        return _service_error(exc)
    return {"deleted": deleted}


@router.get("/attachments/{attachment_id}")
async def download_attachment(attachment_id: str, request: Request):
    s = _session(request)
    if not s:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    from services.tenancy import tenant_context

    def _resolve():
        with tenant_context(s.get("tid", "default")):
            record = attachments.get_attachment(attachment_id, include_private=True)
            if record is None:
                return None, None
            return record, storage.local_path_for(
                record["storage_key"],
                suffix=os.path.splitext(record["name"])[1],
            )

    record, path = await asyncio.to_thread(_resolve)
    if record is None or path is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    cleanup = None
    if settings.storage_backend.lower() in {"s3", "gcs"}:
        cleanup = BackgroundTask(os.remove, path)
    return FileResponse(
        path,
        media_type=record["mimeType"],
        filename=record["name"],
        content_disposition_type="attachment",
        headers={
            "Cache-Control": "private, max-age=300",
            "X-Content-Type-Options": "nosniff",
        },
        background=cleanup,
    )


@router.post("/transcribe")
async def transcribe_voice(
    request: Request,
    audio: UploadFile = File(...),
):
    s = _session(request)
    if not s:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    if rejected := _require_same_origin(request):
        return rejected
    if not transcription.is_configured():
        return JSONResponse(
            {"error": "Voice transcription is not configured.", "code": "voice_unavailable"},
            status_code=503,
        )
    if limited := _rate_limit_response(
        request,
        s.get("tid", "default"),
        "voice",
        int(os.getenv("VOICE_REQUESTS_PER_MINUTE", "8")),
    ):
        return limited
    account = accounts.get_account_by_person(s["pid"])
    plan = (account or {}).get("plan", "free")
    path = ""
    try:
        path, _ = await _spool_upload(audio, transcription.max_bytes(plan))
        mime, _, _ = await asyncio.to_thread(
            attachments.inspect_path,
            path,
            filename=audio.filename or "recording.webm",
            declared_mime=audio.content_type or "",
            plan=plan,
        )
        if not attachments.is_audio_or_video(mime):
            raise attachments.AttachmentError(
                "Voice input must be a supported audio recording.",
                code="unsupported_audio",
                status_code=415,
            )
        await asyncio.to_thread(transcription.validate_media_duration, path)
        with rate_limits.concurrency(
            "transcription",
            limit=int(os.getenv("TRANSCRIPTION_GLOBAL_CONCURRENCY", "20")),
            lease_seconds=int(
                os.getenv("TRANSCRIPTION_CONCURRENCY_LEASE_SECONDS", "180")
            ),
        ):
            text = await asyncio.to_thread(
                transcription.transcribe_path,
                path,
                filename=audio.filename or "recording.webm",
                mime_type=mime,
            )
        return {"text": text}
    except Exception as exc:
        return _service_error(exc)
    finally:
        if path:
            try:
                os.remove(path)
            except OSError:
                pass
