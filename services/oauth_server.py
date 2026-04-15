"""
oauth_server.py — Shared HTTP callback server for Google OAuth flows.

Handles any Google OAuth connector (Calendar+Drive, Gmail, ...) as long as
each flow specifies its own scopes and destination token file.

Flow:
  1. Telegram command calls `create_auth_url(chat_id, scopes, token_path, label)`.
  2. User clicks the returned URL → Google → browser redirects to
     OAUTH_REDIRECT_URI which points at this server's /oauth2callback.
  3. We exchange the code, write the token file, and invoke
     `on_success(chat_id, label)` on the asyncio loop so the bot can DM.
"""

import asyncio
import logging
import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Awaitable, Callable, Optional
from urllib.parse import urlparse, parse_qs

from google_auth_oauthlib.flow import Flow

logger = logging.getLogger(__name__)

_pending: dict[str, dict] = {}
_pending_lock = threading.Lock()

_config = {
    "redirect_uri": "",
    "creds_path": "credentials.json",
    "on_success": None,  # Optional[Callable[[int, str], Awaitable[None]]]
    "loop": None,        # asyncio.AbstractEventLoop
}


def configure(
    redirect_uri: str,
    on_success: Callable[[int, str], Awaitable[None]],
    loop: asyncio.AbstractEventLoop,
    creds_path: str = "credentials.json",
):
    _config["redirect_uri"] = redirect_uri
    _config["on_success"] = on_success
    _config["loop"] = loop
    _config["creds_path"] = creds_path


def create_auth_url(chat_id: int, scopes: list[str], token_path: str, label: str) -> str:
    """Start a fresh Flow and return the URL the user must visit.

    - `scopes` is the list of Google OAuth scopes this connector needs.
    - `token_path` is where the resulting credentials JSON will be written.
    - `label` is a human name used in the Telegram confirmation ("Gmail", ...).
    """
    if not _config["redirect_uri"]:
        raise RuntimeError("OAuth server not configured — set OAUTH_REDIRECT_URI")

    flow = Flow.from_client_secrets_file(_config["creds_path"], scopes=scopes)
    flow.redirect_uri = _config["redirect_uri"]

    state = uuid.uuid4().hex
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    with _pending_lock:
        _pending[state] = {
            "flow": flow,
            "chat_id": chat_id,
            "token_path": token_path,
            "label": label,
        }
    return auth_url


class _OAuthHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        logger.info("oauth_server: " + format, *args)

    def _respond(self, status: int, body: str, content_type: str = "text/html"):
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != "/oauth2callback":
            self._respond(404, "<h1>Not found</h1>")
            return

        qs = parse_qs(parsed.query)
        state = (qs.get("state") or [""])[0]
        code = (qs.get("code") or [""])[0]
        error = (qs.get("error") or [""])[0]

        with _pending_lock:
            entry = _pending.pop(state, None)

        if error:
            self._respond(400, f"<h1>OAuth error</h1><p>{error}</p>")
            return
        if not entry:
            self._respond(400, "<h1>Unknown or expired state</h1><p>Start again from Telegram.</p>")
            return
        if not code:
            self._respond(400, "<h1>Missing authorization code</h1>")
            return

        flow: Flow = entry["flow"]
        chat_id: int = entry["chat_id"]
        token_path: str = entry["token_path"]
        label: str = entry["label"]

        try:
            flow.fetch_token(code=code)
        except Exception as e:
            logger.error("fetch_token failed: %s", e)
            self._respond(500, f"<h1>Token exchange failed</h1><p>{e}</p>")
            return

        creds = flow.credentials
        try:
            with open(token_path, "w") as f:
                f.write(creds.to_json())
        except Exception as e:
            logger.error("Writing %s failed: %s", token_path, e)
            self._respond(500, f"<h1>Could not write {token_path}</h1><p>{e}</p>")
            return

        logger.info("%s OAuth complete for chat_id=%s", label, chat_id)
        self._respond(
            200,
            f"<h1>✅ {label} connected</h1><p>You can close this tab and return to Telegram.</p>",
        )

        on_success = _config["on_success"]
        loop = _config["loop"]
        if on_success and loop:
            try:
                asyncio.run_coroutine_threadsafe(on_success(chat_id, label), loop)
            except Exception as e:
                logger.error("on_success dispatch failed: %s", e)


def start_oauth_server(port: int) -> ThreadingHTTPServer:
    """Start the callback server in a daemon thread. Returns the server."""
    server = ThreadingHTTPServer(("0.0.0.0", port), _OAuthHandler)
    thread = threading.Thread(target=server.serve_forever, name="oauth-server", daemon=True)
    thread.start()
    logger.info("OAuth callback server listening on 0.0.0.0:%d", port)
    return server
