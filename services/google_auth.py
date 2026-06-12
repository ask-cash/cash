"""
google_auth.py — Per-tenant Google OAuth credential loading.

Replaces the ad-hoc `token.json` / `gmail_token.json` file handling scattered
across calendars/, gmail.py and drive.py with a single tenant-aware loader:

  * In production, the token blob lives encrypted in the secret vault
    (services.secrets) keyed per tenant, e.g. "google_token", "gmail_token".
  * Locally (no DB / no encryption key) it falls back to the legacy on-disk
    token file so `scripts/auth_google.py` and single-tenant dev keep working.

Refreshed tokens are written back to whichever source they came from. The
service builders never launch an interactive browser flow — connecting is done
through the gateway's OAuth web flow (or scripts/auth_google.py locally).
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from services import secrets as secret_vault
from services.config import settings

logger = logging.getLogger(__name__)


def _use_vault() -> bool:
    return settings.secrets_backend.lower() == "db" and bool(settings.secrets_encryption_key)


def save_credentials(secret_name: str, creds: Credentials, legacy_token_path: str) -> None:
    blob = creds.to_json()
    if _use_vault():
        secret_vault.set_secret(secret_name, blob)
    else:
        with open(legacy_token_path, "w") as f:
            f.write(blob)


def save_token_json(secret_name: str, creds_json: str, legacy_token_path: str) -> None:
    """Persist a raw token JSON string (used by the OAuth callback)."""
    if _use_vault():
        secret_vault.set_secret(secret_name, creds_json)
    else:
        with open(legacy_token_path, "w") as f:
            f.write(creds_json)


def load_credentials(
    secret_name: str,
    scopes: list[str],
    legacy_token_path: str,
) -> Optional[Credentials]:
    """Load (and refresh) credentials for the active tenant, or None if absent."""
    creds: Optional[Credentials] = None

    if _use_vault():
        info = secret_vault.get_json(secret_name)
        if info:
            creds = Credentials.from_authorized_user_info(info, scopes)
    elif os.path.exists(legacy_token_path):
        creds = Credentials.from_authorized_user_file(legacy_token_path, scopes)

    if creds is None:
        return None

    if not creds.valid and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            save_credentials(secret_name, creds, legacy_token_path)
        except Exception:
            logger.exception("Failed refreshing Google credentials (%s)", secret_name)
            return None

    return creds
