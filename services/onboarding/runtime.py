"""
runtime.py — The decision the platform handlers call on every inbound message.

``route(event, person_id)`` is the single entry point. It answers: should this
message be handled by onboarding, or handed to the assistant?

  * Owner messages          -> never onboarded (returns PASS).
  * Onboarding disabled      -> PASS.
  * Public (non-DM) channels -> PASS (we don't collect emails in the open; the
    existing public-channel behavior is preserved).
  * Active customer          -> PASS (assistant mode).
  * New / mid-onboarding     -> HANDLED, with the reply text to send.

When the in-chat flow finishes collecting basics, the runtime mints the secure
setup link (services.onboarding.links) and appends it to the reply. It persists
profile changes (services.onboarding.profiles). The handler just sends the text.

This is platform-agnostic: it takes the normalized IncomingEvent, so Telegram,
Discord, Slack and Teams share the exact same onboarding behavior.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from services.config import settings
from services.onboarding import flow as onboarding_flow
from services.onboarding import links as onboarding_links
from services.onboarding import profiles as onboarding_profiles
from services.tenancy import current_tenant_id

logger = logging.getLogger(__name__)


@dataclass
class RouteResult:
    handled: bool                 # True -> onboarding produced a reply; stop here
    reply: Optional[str] = None   # text to send when handled
    became_active: bool = False   # profile flipped to active this turn (rare)


def _pass() -> RouteResult:
    return RouteResult(handled=False)


def route(event, person_id: Optional[str]) -> RouteResult:
    """Decide onboarding vs. assistant for one inbound event.

    `event` is a services.platforms.base.IncomingEvent (only `.is_owner` and
    `.is_direct` and `.text` are read, so any object with those attrs works).
    Best-effort: on any internal error we PASS to the assistant rather than trap
    a user in a broken onboarding loop.
    """
    if not settings.onboarding_enabled:
        return _pass()
    # The owner is the operator, never a customer to onboard.
    if getattr(event, "is_owner", False):
        return _pass()
    if not person_id:
        # No identity resolved — can't attach a profile; let normal flow run.
        return _pass()
    # Onboarding (which asks for an email) only happens in direct/1:1 chats.
    if not getattr(event, "is_direct", False):
        return _pass()

    try:
        profile = onboarding_profiles.get_or_create(person_id)
        if profile.is_active:
            return _pass()

        result = onboarding_flow.advance(profile, getattr(event, "text", "") or "")
        reply = result.reply

        if result.link_required:
            link = onboarding_links.make_link(person_id, tenant_id=current_tenant_id())
            reply = f"{reply}\n\n{link}"
            if not result.profile.link_issued_at:
                from datetime import datetime, timezone
                result.profile.link_issued_at = datetime.now(timezone.utc).isoformat()

        onboarding_profiles.save_profile(result.profile)
        if result.collection_complete:
            logger.info("[onboarding] collected basics for person=%s", person_id)
        return RouteResult(handled=True, reply=reply)
    except Exception:
        logger.exception("[onboarding] route failed for person=%s — passing through", person_id)
        return _pass()
