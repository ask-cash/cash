"""
directives_commands.py — Telegram slash commands for managing directives.

Commands (all gated to Suhail via main.py's owner_only wrapper):

  /directives              List active directives.
  /unignore <hint>         Revoke ignore directives targeting that person.
  /forget   <hint>         Revoke ALL active directives targeting that person.
  /revoke   <directive_id> Revoke a specific directive by id.

`<hint>` accepts a display name, @handle, canonical name, or a person_id.
"""

import asyncio
import logging
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from services.directives import store as directives_store
from services.identity import people as identity_people

logger = logging.getLogger(__name__)

MAX_DIRECTIVES_LISTED = 25
MAX_TELEGRAM_REPLY = 3900  # Telegram's hard limit is 4096; leave headroom.


def _short_id(directive_id: str) -> str:
    return directive_id[:16]


def _scope_phrase(d) -> str:
    parts = []
    if d.scope_platform != "*":
        parts.append(f"platform={d.scope_platform}")
    if d.scope_workspace != "*":
        parts.append(f"workspace={d.scope_workspace}")
    if d.scope_channel != "*":
        parts.append(f"channel={d.scope_channel}")
    return " ".join(parts) if parts else "(global)"


def _target_label(d) -> str:
    if d.target_person_id is None:
        return "(scope-only)"
    p = identity_people.get_person(d.target_person_id)
    if p and p.canonical_name:
        return f"{p.canonical_name}"
    return d.target_person_id


def _format_directive_line(d) -> str:
    expires = f" expires={d.expires_at[:10]}" if d.expires_at else ""
    return (
        f"• `{_short_id(d.directive_id)}`  *{d.action}*  →  "
        f"{_target_label(d)}  [{_scope_phrase(d)}]{expires}"
    )


def _resolve_hint_to_one(hint: str) -> tuple[Optional[object], Optional[str]]:
    """Resolve a hint to (person, error_message). One of the two is None."""
    candidates = identity_people.find_by_hint(hint)
    if not candidates:
        return None, f"🐾 No one matches '{hint}'."
    if len(candidates) > 1:
        names = "\n".join(f"  • {p.canonical_name} ({p.person_id})" for p in candidates[:5])
        return None, f"🐾 Multiple match '{hint}':\n{names}\n\nRetry with the exact handle or paste the person_id."
    return candidates[0], None


# ---------------------------------------------------------------------------
# /directives
# ---------------------------------------------------------------------------

async def cmd_directives(update: Update, context: ContextTypes.DEFAULT_TYPE):
    actives = await asyncio.to_thread(directives_store.list_active)
    if not actives:
        await update.message.reply_text("🐾 No active directives.")
        return

    lines = ["🐾 *Active directives:*"]
    for d in actives[:MAX_DIRECTIVES_LISTED]:
        lines.append(_format_directive_line(d))
    if len(actives) > MAX_DIRECTIVES_LISTED:
        lines.append(f"\n…and {len(actives) - MAX_DIRECTIVES_LISTED} more.")

    body = "\n".join(lines)
    if len(body) > MAX_TELEGRAM_REPLY:
        body = body[:MAX_TELEGRAM_REPLY - 3] + "..."
    await update.message.reply_text(body, parse_mode="Markdown")


# ---------------------------------------------------------------------------
# /revoke <directive_id>
# ---------------------------------------------------------------------------

async def cmd_revoke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Usage: `/revoke <directive_id>`\n\nUse /directives to see ids.",
            parse_mode="Markdown",
        )
        return
    directive_id = args[0].strip()
    revoked = await asyncio.to_thread(directives_store.revoke, directive_id)
    if revoked:
        await update.message.reply_text(f"🐾 Revoked `{directive_id}`.", parse_mode="Markdown")
    else:
        await update.message.reply_text(
            f"🐾 No active directive with id `{directive_id}` — already revoked, expired, or not found.",
            parse_mode="Markdown",
        )


# ---------------------------------------------------------------------------
# /unignore <hint>
# ---------------------------------------------------------------------------

async def cmd_unignore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: `/unignore <name | @handle | person_id>`", parse_mode="Markdown")
        return
    hint = " ".join(args).strip()

    target, err = await asyncio.to_thread(_resolve_hint_to_one, hint)
    if err:
        await update.message.reply_text(err)
        return

    active = await asyncio.to_thread(directives_store.list_active_for_person, target.person_id)
    revoked = 0
    for d in active:
        if d.action == "ignore":
            if directives_store.revoke(d.directive_id):
                revoked += 1
    if revoked:
        await update.message.reply_text(
            f"🐾 Revoked {revoked} ignore directive(s) for *{target.canonical_name}*. "
            f"I'll respond to them again.",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            f"🐾 No active ignore directives for *{target.canonical_name}*.",
            parse_mode="Markdown",
        )


# ---------------------------------------------------------------------------
# /forget <hint>
# ---------------------------------------------------------------------------

async def cmd_forget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: `/forget <name | @handle | person_id>`", parse_mode="Markdown")
        return
    hint = " ".join(args).strip()

    target, err = await asyncio.to_thread(_resolve_hint_to_one, hint)
    if err:
        await update.message.reply_text(err)
        return

    active = await asyncio.to_thread(directives_store.list_active_for_person, target.person_id)
    revoked = 0
    for d in active:
        # Only revoke directives that *target this person*. Scope-only
        # directives (target_person_id IS NULL) that happened to surface in
        # the per-person list affect everyone in scope; they shouldn't be
        # revoked by a forget-this-one operation.
        if d.target_person_id == target.person_id:
            if directives_store.revoke(d.directive_id):
                revoked += 1
    if revoked:
        await update.message.reply_text(
            f"🐾 Revoked {revoked} directive(s) targeting *{target.canonical_name}*. "
            f"They start with a clean slate.",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            f"🐾 No active directives targeting *{target.canonical_name}*.",
            parse_mode="Markdown",
        )
