"""
tokens.py — the TokenManager over the secrets vault (Feature 7).

A uniform accessor for every provider's credentials so capability code never
plumbs raw tokens: ``is_connected`` / ``credentials`` / ``store_token`` /
``disconnect``. Google credentials are loaded through ``services.google_auth``,
which already **auto-refreshes** an expired token and writes the refreshed blob
back to the vault — so refresh-on-expiry is reused, not reinvented. Non-OAuth
providers (Outlook device-code, Discord account-link) report connectivity
best-effort; they own their own caches.

Everything degrades to "not connected" rather than raising, so a vault or
provider hiccup can never crash a connect-status check.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from services import secrets as secret_vault
from services.integrations import registry

logger = logging.getLogger(__name__)


def _token_blob(secret_name: Optional[str], legacy_path: Optional[str]) -> Optional[dict | str]:
    """Return the stored token (vault first, then legacy on-disk), or None."""
    if secret_name:
        try:
            blob = secret_vault.get_json(secret_name)
            if blob:
                return blob
            raw = secret_vault.get_secret(secret_name)
            if raw:
                return raw
        except Exception:
            logger.exception("token vault read failed for %s", secret_name)
    if legacy_path and os.path.exists(legacy_path):
        return legacy_path
    return None


def _outlook_connected(p: registry.Provider) -> bool:
    # MSAL keeps a serialized cache on disk; presence of a non-empty cache with
    # an account is our best-effort "connected" signal, checked defensively.
    path = p.legacy_token_path
    return bool(path and os.path.exists(path) and os.path.getsize(path) > 0)


def _discord_connected(p: registry.Provider) -> bool:
    # Discord is "connected" once a Discord account has been seen/linked for this
    # tenant — i.e. a discord platform_identity row exists. Best-effort; any
    # identity/DB hiccup reports "not connected" rather than raising.
    try:
        from services.identity.store import connect
        with connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM platform_identities WHERE platform = 'discord' LIMIT 1"
            ).fetchone()
        return row is not None
    except Exception:
        return False


def is_connected(provider_id: str) -> bool:
    """True if the provider currently has usable credentials for this tenant."""
    p = registry.get(provider_id)
    if p is None or not p.available:
        return False
    if p.is_oauth:
        return _token_blob(p.secret_name, p.legacy_token_path) is not None
    if p.auth == registry.AUTH_DEVICE_CODE:
        return _outlook_connected(p)
    if p.auth == registry.AUTH_ACCOUNT_LINK:
        return _discord_connected(p)
    return False


def connected_providers() -> list[str]:
    """Ids of every provider currently connected for this tenant."""
    return [p.id for p in registry.all_providers() if is_connected(p.id)]


def credentials(provider_id: str):
    """Refreshed credentials for an OAuth provider, or None.

    Delegates to ``services.google_auth.load_credentials`` (which refreshes an
    expired token and persists the new blob). Returns None for non-OAuth or
    unconnected providers so callers uniformly handle "no creds".
    """
    p = registry.get(provider_id)
    if p is None or not p.is_oauth or not p.secret_name:
        return None
    from services.google_auth import load_credentials
    return load_credentials(p.secret_name, list(p.scopes), p.legacy_token_path or "")


def store_token(provider_id: str, creds_json: str) -> None:
    """Persist a freshly minted OAuth token blob into the vault + legacy file.

    The single write path the gateway OAuth callback can route through so every
    provider's tokens land in one place (keyed by the registry's secret_name).
    """
    p = registry.get(provider_id)
    if p is None or not p.secret_name:
        raise ValueError(f"provider {provider_id!r} has no vault token to store")
    from services.google_auth import save_token_json
    save_token_json(p.secret_name, creds_json, p.legacy_token_path or "")


def disconnect(provider_id: str) -> bool:
    """Delete a provider's stored token. True if a token store existed to clear."""
    p = registry.get(provider_id)
    if p is None:
        return False
    cleared = False
    if p.secret_name:
        try:
            secret_vault.delete_secret(p.secret_name)
            cleared = True
        except Exception:
            logger.exception("failed clearing vault token for %s", provider_id)
    if p.legacy_token_path and os.path.exists(p.legacy_token_path):
        try:
            os.remove(p.legacy_token_path)
            cleared = True
        except Exception:
            logger.exception("failed removing legacy token for %s", provider_id)
    return cleared
