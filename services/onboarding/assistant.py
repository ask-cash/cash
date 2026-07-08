"""
assistant.py — Reply path for an ALREADY-onboarded (active) customer.

Critical boundary: this must NOT reach the owner's private assistant
(``services.ai_brain``), which loads Suhail's calendar, tasks, trading rules and
memory. A customer talking to Cash gets *their own* scoped assistant — their
profile, their per-person conversation memory, their connected integrations —
and never the operator's data.

Today this provides the conversational layer (recognise the customer, answer,
take notes, tell them what it can do based on what they've connected). Executing
real calendar/drive/gmail actions per-customer requires per-customer OAuth token
plumbing — see docs; the connect step already stores those tokens, and this is
where they'd be used. Until then the assistant is explicit about what's wired.
"""

from __future__ import annotations

import logging
from typing import Optional

from services import persona
from services.composer import base as composer_base
from services.onboarding.profiles import CustomerProfile, KNOWN_INTEGRATIONS

logger = logging.getLogger(__name__)

_SYSTEM = persona.persona_system_block("customer") + """

You help them with scheduling, reminders, managing files, email, and answering questions.

Rules:
- Use what you know about them (their name, timezone, and what they wanted help with) to be relevant.
- Only claim to take an action (create an event, save a file, send an email) if the CONNECTED INTEGRATIONS list says that integration is connected. If they ask for something that needs an integration they haven't connected, tell them to connect it first and offer the setup link.
- Match the user's language and tone."""


def _capabilities_line(profile: CustomerProfile) -> str:
    connected = [i for i in KNOWN_INTEGRATIONS if profile.connected(i)]
    if not connected:
        return "CONNECTED INTEGRATIONS: none yet (so you cannot perform calendar/drive/email actions — ask them to finish setup first)."
    return "CONNECTED INTEGRATIONS: " + ", ".join(connected)


def customer_reply(profile: CustomerProfile, person_id: str, text: str) -> str:
    """Compose a scoped assistant reply for an active customer.

    Synchronous (Anthropic call); wrap in asyncio.to_thread from async callers.
    Falls back to a safe canned line if the model call fails.
    """
    ctx = composer_base.build_person_context(person_id)
    memory_block = composer_base.render_context_block(ctx)

    profile_block = (
        f"=== WHO YOU'RE TALKING TO ===\n"
        f"name: {profile.name or 'unknown'}\n"
        f"timezone: {profile.timezone or 'unknown'}\n"
        f"wants help with: {profile.use_case or 'general assistance'}\n"
        f"{_capabilities_line(profile)}"
    )
    user_block = profile_block
    if memory_block:
        user_block += f"\n\n{memory_block}"
    user_block += f"\n\n=== THEIR MESSAGE ===\n{text}\n\nReply as Cash, their assistant."

    try:
        return composer_base.complete(system=_SYSTEM, user_block=user_block, max_tokens=500)
    except Exception:
        logger.exception("[onboarding] customer_reply LLM call failed for %s", person_id)
        name = profile.name or "there"
        return f"Hi {name}, I'm here — I hit a brief error on that one. Could you try again?"
