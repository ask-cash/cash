"""Customer onboarding for Cash.

Cash is a multi-customer assistant: anyone who messages it on Telegram,
Discord, or another connected platform is either an existing customer (whose
platform identity already maps to an internal profile) or a brand-new person.

This package owns that distinction and the new-user journey:

  * ``profiles``  — the CustomerProfile record (status, name, email, timezone,
    use case, connected integrations) persisted per ``person_id``.
  * ``flow``      — the pure in-chat onboarding state machine (ask name -> email
    -> timezone -> use case -> issue setup link).
  * ``links``     — signed, expiring onboarding links for the web setup step.
  * ``runtime``   — the glue the platform handlers call: given an inbound event,
    decide whether to onboard or hand off to the assistant.

The platform <-> person mapping itself lives in ``services.identity`` (the
``people`` / ``platform_identities`` tables); onboarding hangs a profile off the
``person_id`` that layer resolves.
"""

from services.onboarding.profiles import (  # noqa: F401
    STATUS_ACTIVE,
    STATUS_AWAITING_SETUP,
    STATUS_COLLECTING,
    STATUS_NEW,
    CustomerProfile,
    get_profile,
    is_registered,
    save_profile,
)

__all__ = [
    "CustomerProfile",
    "get_profile",
    "save_profile",
    "is_registered",
    "STATUS_NEW",
    "STATUS_COLLECTING",
    "STATUS_AWAITING_SETUP",
    "STATUS_ACTIVE",
]
