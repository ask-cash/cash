"""
accounts.py — dashboard user accounts (the web identity provider).

A web signup creates: a control-plane ``accounts`` row (email + salted password
hash + profile), a dedicated **tenant** (so each user's data is RLS-isolated like
every other tenant), and a **person** in that tenant (platform ``web``). The
signed dashboard session then carries (person_id, tenant_id), exactly like the
magic-link flow, so every downstream service (memory, calendar, secrets vault)
is tenant-scoped for free.

Passwords are hashed with PBKDF2-HMAC-SHA256 (stdlib) — no plaintext is ever
stored. The ``accounts`` table is control-plane (queried under system context,
no RLS), mirroring ``tenants`` / ``tenant_secrets``.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import secrets as _secrets
from typing import Optional

from services import tenant_registry
from services.db import connect
from services.identity import people as identity_people
from services.tenancy import system_context, tenant_context

logger = logging.getLogger(__name__)

_PBKDF2_ROUNDS = 200_000


# ---------------------------------------------------------------------------
# Password hashing (PBKDF2-HMAC-SHA256, stdlib)
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    salt = _secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _PBKDF2_ROUNDS)
    return f"pbkdf2${_PBKDF2_ROUNDS}${salt}${dk.hex()}"


def verify_password(password: str, stored: Optional[str]) -> bool:
    if not stored:
        return False
    try:
        algo, rounds, salt, digest = stored.split("$")
        if algo != "pbkdf2":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(rounds))
        return _secrets.compare_digest(dk.hex(), digest)
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _row_to_account(row) -> dict:
    return {
        "email": row["email"],
        "first_name": row["first_name"] or "",
        "last_name": row["last_name"] or "",
        "tenant_id": row["tenant_id"],
        "person_id": row["person_id"],
        "role": row["role"],
        "platforms": json.loads(row["platforms"]) if row["platforms"] else [],
        "onboarded": bool(row["onboarded"]),
        "plan": (row["plan"] or "free") if "plan" in row.keys() else "free",
        "auth_provider": row["auth_provider"],
    }


def get_account(email: str) -> Optional[dict]:
    email = (email or "").strip().lower()
    if not email:
        return None
    with system_context():
        with connect() as conn:
            row = conn.execute("SELECT * FROM accounts WHERE email = ?", (email,)).fetchone()
    return _row_to_account(row) if row else None


def get_account_by_person(person_id: str) -> Optional[dict]:
    """Resolve the account behind a session's person_id (control-plane lookup)."""
    if not person_id:
        return None
    with system_context():
        with connect() as conn:
            row = conn.execute("SELECT * FROM accounts WHERE person_id = ?", (person_id,)).fetchone()
    return _row_to_account(row) if row else None


def _password_hash(email: str) -> Optional[str]:
    with system_context():
        with connect() as conn:
            row = conn.execute("SELECT password_hash FROM accounts WHERE email = ?", (email,)).fetchone()
    return row["password_hash"] if row else None


def create_account(
    email: str,
    password: Optional[str],
    first_name: str,
    last_name: str = "",
    *,
    auth_provider: str = "password",
) -> dict:
    """Create a user + their tenant + their person. Raises ValueError if the
    email already exists. ``password`` may be None for OAuth-only accounts."""
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise ValueError("a valid email is required")
    if get_account(email):
        raise ValueError("an account with that email already exists")

    display = " ".join(p for p in (first_name, last_name) if p).strip() or email

    # A dedicated tenant per user, then a person inside it.
    with system_context():
        tenant_id = tenant_registry.new_tenant_id()
        tenant_registry.ensure_tenant(tenant_id, display_name=display, timezone="Asia/Kolkata")
    with tenant_context(tenant_id):
        person_id = identity_people.resolve(
            platform="web", platform_user_id=email, display_name=display, handle=email,
        )

    pw_hash = hash_password(password) if password else None
    with system_context():
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO accounts
                    (email, password_hash, first_name, last_name, tenant_id, person_id,
                     role, platforms, onboarded, auth_provider, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (email, pw_hash, first_name, last_name, tenant_id, person_id,
                 None, None, False, auth_provider, _now_iso()),
            )
    logger.info("[accounts] created %s (tenant=%s person=%s)", email, tenant_id, person_id)
    return get_account(email)  # type: ignore[return-value]


def verify_login(email: str, password: str) -> Optional[dict]:
    """Return the account if the password matches, else None."""
    email = (email or "").strip().lower()
    if not verify_password(password, _password_hash(email)):
        return None
    return get_account(email)


def get_or_create_oauth_account(email: str, first_name: str = "", last_name: str = "") -> dict:
    """Resolve (or create) a password-less account for an OAuth (e.g. Google) login."""
    existing = get_account(email)
    if existing:
        return existing
    return create_account(email, None, first_name, last_name, auth_provider="google")


def update_profile(email: str, **fields) -> Optional[dict]:
    """Patch profile columns (first_name, last_name, role, platforms, onboarded)."""
    email = (email or "").strip().lower()
    allowed = {"first_name", "last_name", "role", "platforms", "onboarded"}
    sets, vals = [], []
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k == "platforms" and v is not None:
            v = json.dumps(v)
        if k == "onboarded":
            v = bool(v)
        sets.append(f"{k} = ?")
        vals.append(v)
    if not sets:
        return get_account(email)
    vals.append(email)
    with system_context():
        with connect() as conn:
            conn.execute(f"UPDATE accounts SET {', '.join(sets)} WHERE email = ?", vals)
    return get_account(email)
