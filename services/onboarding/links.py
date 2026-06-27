"""
links.py — Signed, expiring onboarding links.

After Cash collects a new customer's basics in chat, it hands them a URL to a
web page where they connect Google Calendar / Drive / Gmail. That URL must be:

  * unguessable — so a stranger can't open someone else's setup page, and
  * expiring    — so a leaked link stops working.

We sign a compact payload (person_id, tenant_id, expiry) with HMAC-SHA256 and
base64url-encode it. No DB lookup is needed to validate — verification is a
constant-time signature check plus an expiry check. Pure functions, trivially
unit-testable; the only environment dependency is the signing secret.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Optional

from services.config import settings

logger = logging.getLogger(__name__)

# Dev fallback only. Set ONBOARDING_SIGNING_SECRET (or SECRETS_ENCRYPTION_KEY)
# in any real deployment — a predictable secret makes links forgeable.
_DEV_FALLBACK_SECRET = "cash-dev-onboarding-secret-change-me"


def _signing_secret() -> bytes:
    secret = (
        settings.onboarding_signing_secret
        or settings.secrets_encryption_key
        or _DEV_FALLBACK_SECRET
    )
    return secret.encode("utf-8")


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def make_token(
    person_id: str,
    *,
    tenant_id: str = "default",
    ttl_hours: Optional[int] = None,
    now: Optional[float] = None,
) -> str:
    """Return a signed `payload.signature` token for this person."""
    if not person_id:
        raise ValueError("person_id is required")
    ttl = ttl_hours if ttl_hours is not None else settings.onboarding_link_ttl_hours
    issued = now if now is not None else time.time()
    payload = {
        "pid": person_id,
        "tid": tenant_id or "default",
        "exp": int(issued + ttl * 3600),
    }
    payload_b = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    body = _b64e(payload_b)
    sig = hmac.new(_signing_secret(), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64e(sig)}"


def verify_token(token: str, *, now: Optional[float] = None) -> Optional[dict]:
    """Return the payload dict if the token is valid and unexpired, else None.

    Never raises — a malformed or tampered token is just invalid.
    """
    if not token or "." not in token:
        return None
    body, _, sig_part = token.partition(".")
    try:
        expected = hmac.new(_signing_secret(), body.encode("ascii"), hashlib.sha256).digest()
        provided = _b64d(sig_part)
    except Exception:
        return None
    if not hmac.compare_digest(expected, provided):
        return None
    try:
        payload = json.loads(_b64d(body))
    except Exception:
        return None
    exp = payload.get("exp")
    clock = now if now is not None else time.time()
    if not isinstance(exp, int) or clock >= exp:
        return None
    if not payload.get("pid"):
        return None
    return payload


def make_link(person_id: str, *, tenant_id: str = "default", base_url: Optional[str] = None) -> str:
    """Build the full onboarding URL for a person.

    Uses ``PUBLIC_BASE_URL`` when set; otherwise returns a relative path the
    caller can prefix. The web route lives at ``/onboard/{token}`` on the gateway.
    """
    token = make_token(person_id, tenant_id=tenant_id)
    base = (base_url if base_url is not None else settings.public_base_url).rstrip("/")
    path = f"/onboard/{token}"
    return f"{base}{path}" if base else path
