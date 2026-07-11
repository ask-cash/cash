"""
registry.py — Cash's integration registry (Feature 7).

One declarative catalogue of every provider Cash can connect to: its OAuth style,
scopes, where its token lives in the ``secrets`` vault, how to start a connect
flow, and — the link to Feature 6 — which **skill packs** it unlocks. This is
Cash's adaptation of Vellum's integration catalogue, generalizing the ad-hoc
Google/Outlook/Discord connect paths that were scattered across
``google_auth.py``, ``oauth_server.py`` and ``bot/handlers/commands.py``.

The registry is pure data + lookups; token storage/refresh lives in
``services.integrations.tokens`` (the TokenManager) over ``services.secrets``.

Scopes here are the intended single source of truth; the capability modules
(``calendars.google_calendar``, ``services.gmail``, ``calendars.outlook_calendar``)
currently define matching constants and will be pointed here over time.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

# Auth styles.
AUTH_GOOGLE_OAUTH = "google_oauth"   # web OAuth via the gateway callback
AUTH_DEVICE_CODE = "device_code"     # MSAL device-code flow (Outlook)
AUTH_ACCOUNT_LINK = "account_link"   # signed-link identity fold (Discord DM)
AUTH_PLANNED = "planned"             # documented, not yet wired in Cash


@dataclass(frozen=True)
class Provider:
    """One connectable integration."""

    id: str
    title: str
    auth: str
    unlocks: tuple[str, ...]           # skill-pack ids this provider unlocks
    scopes: tuple[str, ...] = ()
    secret_name: Optional[str] = None  # vault key holding the token blob
    legacy_token_path: Optional[str] = None  # on-disk fallback (local dev)
    connect_hint: str = ""             # command / instruction to connect
    available: bool = True             # False = documented but not yet wired

    @property
    def is_oauth(self) -> bool:
        return self.auth in (AUTH_GOOGLE_OAUTH,)


def _google_token_path() -> str:
    return os.getenv("GOOGLE_TOKEN_PATH", "token.json")


def _gmail_token_path() -> str:
    return os.getenv("GMAIL_TOKEN_PATH", "gmail_token.json")


# Scopes mirror the capability modules exactly (single source going forward).
_GOOGLE_SCOPES = (
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive.file",
)
_GMAIL_SCOPES = (
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
)
_OUTLOOK_SCOPES = ("Calendars.ReadWrite", "User.Read")


_PROVIDERS: dict[str, Provider] = {}


def register(provider: Provider) -> Provider:
    _PROVIDERS[provider.id] = provider
    return provider


def _seed() -> None:
    """Register the built-in providers (idempotent)."""
    register(Provider(
        id="google_calendar",
        title="Google Calendar & Drive",
        auth=AUTH_GOOGLE_OAUTH,
        unlocks=("calendar", "calendars_status", "files"),
        scopes=_GOOGLE_SCOPES,
        secret_name="google_token",
        legacy_token_path=_google_token_path(),
        connect_hint="/connect_google",
    ))
    register(Provider(
        id="gmail",
        title="Gmail",
        auth=AUTH_GOOGLE_OAUTH,
        unlocks=("email",),
        scopes=_GMAIL_SCOPES,
        secret_name="gmail_token",
        legacy_token_path=_gmail_token_path(),
        connect_hint="/connect_gmail",
    ))
    register(Provider(
        id="outlook",
        title="Outlook Calendar",
        auth=AUTH_DEVICE_CODE,
        unlocks=("calendar", "calendars_status"),
        scopes=_OUTLOOK_SCOPES,
        secret_name=None,  # MSAL keeps its own serialized cache
        legacy_token_path=os.getenv("OUTLOOK_TOKEN_PATH", "outlook_token.json"),
        connect_hint="/connect_outlook",
    ))
    register(Provider(
        id="discord",
        title="Discord",
        auth=AUTH_ACCOUNT_LINK,
        unlocks=("cross_platform",),
        connect_hint="Open the dashboard and DM Cash the /link code",
    ))
    register(Provider(
        id="telegram",
        title="Telegram",
        auth=AUTH_ACCOUNT_LINK,
        unlocks=("cross_platform",),
        connect_hint="Message the Cash bot on Telegram to link your account",
    ))
    # Documented in doc/ but not yet wired into Cash — surfaced so the dashboard
    # can show the full catalogue with an honest "coming soon" state.
    for pid, title, packs in (
        ("slack", "Slack", ("cross_platform",)),
        ("notion", "Notion", ()),
        ("hubspot", "HubSpot", ()),
        ("linear", "Linear", ()),
        ("twitter", "Twitter / X", ()),
    ):
        register(Provider(
            id=pid, title=title, auth=AUTH_PLANNED, unlocks=packs,
            available=False, connect_hint="Coming soon",
        ))


_seed()


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

def all_providers() -> list[Provider]:
    return list(_PROVIDERS.values())


def get(provider_id: str) -> Optional[Provider]:
    return _PROVIDERS.get(provider_id)


def available_providers() -> list[Provider]:
    """Providers Cash can actually connect today."""
    return [p for p in _PROVIDERS.values() if p.available]


def providers_unlocking(pack_id: str) -> list[Provider]:
    """Every provider whose connection unlocks ``pack_id``."""
    return [p for p in _PROVIDERS.values() if pack_id in p.unlocks]


def connect_url(provider_id: str) -> Optional[str]:
    """A connect instruction/URL for the provider (the hint today).

    Kept as a single entry point so the dashboard (Feature 14) and the Telegram
    commands share one source for "how do I connect X".
    """
    p = get(provider_id)
    return p.connect_hint if p else None
