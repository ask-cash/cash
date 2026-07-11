"""
secrets_exec.py — a scoped executor for authenticated calls.

The guarantee: the model (and the logs, and the returned result) never see a
plaintext secret. Brain/capability code passes a **handle** — the vault key name,
never the value — plus a request or command spec. This module fetches the secret
from the vault, injects it at the boundary, runs the call against an allowlisted
target, and returns only a **scrubbed** result.

Two entry points:
  * ``run_authenticated_request(handle, spec)`` — an HTTP call; the secret is
    injected as a bearer token / header / query param and the host is checked
    against an allowlist.
  * ``run_authenticated_command(handle, argv)`` — a subprocess; the secret is
    passed via an env var (never argv, which is visible in the process list) and
    the executable is allowlisted.

Both default-deny (no host/command is allowed unless configured) and scrub the
secret out of every returned field. Process-level isolation (a separate worker)
is a future phase; the interface here is stable so that swap stays transparent.
"""

from __future__ import annotations

import logging
import os
import subprocess
from urllib.parse import urlparse

from services import secrets as secret_vault

logger = logging.getLogger(__name__)

_REDACTION = "***"


def _env_set(name: str) -> set[str]:
    return {p.strip() for p in os.getenv(name, "").split(",") if p.strip()}


# Default-deny allowlists, extendable per deployment (env) or per call (spec).
ALLOWED_HOSTS: set[str] = _env_set("SECRETS_EXEC_ALLOWED_HOSTS")
ALLOWED_COMMANDS: set[str] = _env_set("SECRETS_EXEC_ALLOWED_COMMANDS")


class SecretsExecError(Exception):
    """Base error for the secrets executor."""


class NotAllowed(SecretsExecError):
    """The requested host/command/injection is not on the allowlist."""


class MissingSecret(SecretsExecError):
    """No secret is stored under the given handle."""


def _scrub(text: str, *secrets: str) -> str:
    """Replace every occurrence of each secret with the redaction marker."""
    if not text:
        return text or ""
    for s in secrets:
        if s:
            text = text.replace(s, _REDACTION)
    return text


def _host_allowed(host: str | None, extra: list[str] | None) -> bool:
    if not host:
        return False
    return host in (ALLOWED_HOSTS | set(extra or []))


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _default_transport(method, url, headers, params, json_body):
    import requests
    return requests.request(method, url, headers=headers, params=params,
                            json=json_body, timeout=30)


def run_authenticated_request(handle: str, spec: dict, *, transport=None) -> dict:
    """Run one authenticated HTTP request and return a scrubbed result.

    ``spec``: ``{"method", "url", "headers", "params", "json",
    "inject": {"where": "bearer|header|query", "name": ...},
    "allow_hosts": [...]}``. The secret under ``handle`` is injected per
    ``inject`` (default: ``Authorization: Bearer <secret>``). Host must be
    allowlisted (globally or via ``allow_hosts``). Returns
    ``{"status_code", "ok", "text"}`` with the secret scrubbed.
    """
    url = spec.get("url", "")
    host = urlparse(url).hostname
    if not _host_allowed(host, spec.get("allow_hosts")):
        raise NotAllowed(f"host not allowed: {host!r}")

    secret = secret_vault.get_secret(handle)
    if not secret:
        raise MissingSecret(f"no secret stored under {handle!r}")

    headers = dict(spec.get("headers") or {})
    params = dict(spec.get("params") or {})
    inject = spec.get("inject") or {"where": "bearer", "name": "Authorization"}
    where = inject.get("where", "bearer")
    name = inject.get("name") or "Authorization"
    if where == "bearer":
        headers[name] = f"Bearer {secret}"
    elif where == "header":
        headers[name] = secret
    elif where == "query":
        params[name] = secret
    else:
        raise NotAllowed(f"unknown injection site: {where!r}")

    transport = transport or _default_transport
    try:
        resp = transport(spec.get("method", "GET").upper(), url, headers, params, spec.get("json"))
    except Exception as e:
        # Scrub in case the exception text echoes the URL/params with the secret.
        raise SecretsExecError(_scrub(str(e), secret)) from None

    status = getattr(resp, "status_code", 0)
    text = getattr(resp, "text", "") or ""
    return {
        "status_code": status,
        "ok": 200 <= status < 300,
        "text": _scrub(text, secret),
    }


# ---------------------------------------------------------------------------
# Subprocess
# ---------------------------------------------------------------------------

def _default_runner(argv, env):
    merged = {**os.environ, **env}
    return subprocess.run(argv, env=merged, capture_output=True, text=True, timeout=60)


def run_authenticated_command(handle: str, argv: list[str], *, env_name: str,
                              allow_commands: list[str] | None = None,
                              runner=None) -> dict:
    """Run an allowlisted subprocess with the secret injected as an env var.

    The secret under ``handle`` is placed in the environment as ``env_name`` (so
    it never appears in ``argv`` or the process list). ``argv[0]`` must be
    allowlisted. Returns ``{"returncode", "stdout", "stderr"}`` scrubbed.
    """
    if not argv:
        raise NotAllowed("empty argv")
    cmd = argv[0]
    if cmd not in (ALLOWED_COMMANDS | set(allow_commands or [])):
        raise NotAllowed(f"command not allowed: {cmd!r}")

    secret = secret_vault.get_secret(handle)
    if not secret:
        raise MissingSecret(f"no secret stored under {handle!r}")

    runner = runner or _default_runner
    try:
        result = runner(argv, {env_name: secret})
    except Exception as e:
        raise SecretsExecError(_scrub(str(e), secret)) from None

    return {
        "returncode": getattr(result, "returncode", 0),
        "stdout": _scrub(getattr(result, "stdout", "") or "", secret),
        "stderr": _scrub(getattr(result, "stderr", "") or "", secret),
    }
