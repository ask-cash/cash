"""
flow.py — The in-chat onboarding state machine (pure).

Given a CustomerProfile and the user's latest message, decide the next thing
Cash should say and how the profile advances. No I/O, no link generation, no
sending — that's the runtime's job. This keeps the conversational logic
deterministic and table-testable.

Conversation shape:

    (new) first message      -> greet, ask NAME, status=collecting step=name
    answer name              -> ask EMAIL
    answer email (valid)     -> ask TIMEZONE
    answer timezone (valid)  -> ask USE CASE
    answer use case          -> status=awaiting_setup, link_required=True
    (awaiting_setup) message  -> remind + resend link (link_required=True)

Invalid email / timezone re-asks the same question instead of advancing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from services.onboarding.profiles import (
    STATUS_AWAITING_SETUP,
    STATUS_COLLECTING,
    STATUS_NEW,
    CustomerProfile,
)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass
class FlowResult:
    profile: CustomerProfile
    reply: str
    # When True the runtime should append the secure setup link to `reply`.
    link_required: bool = False
    # True on the turn the in-chat Q&A finishes (used for logging/metrics).
    collection_complete: bool = False


def _clean(text: str) -> str:
    return (text or "").strip()


def _valid_timezone(tz: str) -> bool:
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(tz)
        return True
    except Exception:
        return False


def advance(profile: CustomerProfile, message: str) -> FlowResult:
    """Advance onboarding by one user message. Returns the next reply + profile.

    Pure: the same (profile, message) always yields the same result.
    """
    text = _clean(message)

    # First contact — greet and start collecting. The triggering message is not
    # treated as an answer.
    if profile.status == STATUS_NEW:
        profile.status = STATUS_COLLECTING
        profile.step = "name"
        return FlowResult(
            profile,
            "Hi, I'm Cash — your new AI assistant. I'll get you set up in under a "
            "minute. First, what's your name?",
        )

    if profile.status == STATUS_COLLECTING:
        return _collect(profile, text)

    if profile.status == STATUS_AWAITING_SETUP:
        # They pinged again before finishing the web setup.
        return FlowResult(
            profile,
            "You're almost there — I just need you to connect your accounts so I "
            "can start helping. Here's your setup link again:",
            link_required=True,
        )

    # Active or unknown — caller shouldn't route here, but be safe.
    return FlowResult(profile, "")


def _collect(profile: CustomerProfile, text: str) -> FlowResult:
    step = profile.step or "name"

    if step == "name":
        if not text:
            return FlowResult(profile, "What should I call you?")
        profile.name = text[:120]
        profile.step = "email"
        return FlowResult(
            profile,
            f"Nice to meet you, {profile.name}. What's the best email for you?",
        )

    if step == "email":
        if not _EMAIL_RE.match(text):
            return FlowResult(
                profile,
                "That doesn't look like a valid email. Could you send it again? "
                "(e.g. you@example.com)",
            )
        profile.email = text.lower()
        profile.step = "timezone"
        return FlowResult(
            profile,
            "Got it. What timezone are you in? You can send something like "
            "'Asia/Kolkata', 'America/New_York', or 'Europe/London'.",
        )

    if step == "timezone":
        if not _valid_timezone(text):
            return FlowResult(
                profile,
                "I didn't recognize that timezone. Try an IANA name like "
                "'Asia/Kolkata', 'America/New_York', or 'Europe/London'.",
            )
        profile.timezone = text
        profile.step = "use_case"
        return FlowResult(
            profile,
            "Perfect. Last question: what do you mostly want my help with? "
            "(e.g. scheduling, reminders, managing files, email)",
        )

    if step == "use_case":
        if not text:
            return FlowResult(profile, "Just a quick line on what you'd use me for?")
        profile.use_case = text[:280]
        profile.status = STATUS_AWAITING_SETUP
        profile.step = None
        return FlowResult(
            profile,
            f"Thanks, {profile.name or 'there'}. One last step — connect "
            "your Google Calendar, Drive, and Gmail so I can schedule, store files, "
            "and handle email for you. Tap here to finish setup:",
            link_required=True,
            collection_complete=True,
        )

    # Unknown step — restart collection from name defensively.
    profile.step = "name"
    return FlowResult(profile, "Let's start over — what's your name?")
