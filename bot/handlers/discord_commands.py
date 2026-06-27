"""
discord_commands.py — Cash's Discord slash commands.

All commands are gated to DISCORD_SUHAIL_USER_ID. discord.py registers them
on the CommandTree, which the client syncs to allowlisted guilds at boot.

Commands:
  /cash-directives           List active directives (ephemeral, only Suhail).
  /cash-unignore <user>      Revoke ignore directives for the given Discord user.
  /cash-forget   <user>      Revoke ALL active directives targeting that user.

Why guild-scoped sync? Global slash commands take up to an hour to propagate
through Discord's edge. Guild-scoped registrations are instant — perfect for
dev iteration and a single-server use case. If we ever need it everywhere,
flip to global sync once.
"""

import asyncio
import logging
from typing import Optional

import discord
from discord import app_commands

from services.directives import store as directives_store
from services.identity import people as identity_people

logger = logging.getLogger(__name__)


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
    return p.canonical_name if (p and p.canonical_name) else d.target_person_id


def _format_directive_line(d) -> str:
    expires = f"  ⏳ {d.expires_at[:10]}" if d.expires_at else ""
    return (
        f"`{d.directive_id[:16]}` **{d.action}** → {_target_label(d)}  "
        f"_{_scope_phrase(d)}_{expires}"
    )


async def _resolve_discord_user_to_person(
    user: discord.User,
) -> tuple[Optional[object], Optional[str]]:
    """Map a Discord User → Person row. Returns (person, error_message)."""
    pi = await asyncio.to_thread(
        identity_people.find_platform_identity, "discord", str(user.id),
    )
    if pi is None:
        return None, (
            f"No record for {user.mention} yet — they need to interact "
            f"with me at least once before I can act on them."
        )
    person = await asyncio.to_thread(identity_people.get_person, pi.person_id)
    if person is None:
        # Shouldn't happen (FK), but be defensive.
        return None, "Identity row exists but person record is missing — please report this."
    return person, None


def register(tree: app_commands.CommandTree, *, suhail_id: int) -> None:
    """Register all Cash slash commands on the given CommandTree."""

    def _is_suhail(interaction: discord.Interaction) -> bool:
        return interaction.user is not None and interaction.user.id == suhail_id

    @tree.command(
        name="cash-directives",
        description="List Cash's active directives (Suhail only).",
    )
    async def cash_directives(interaction: discord.Interaction):
        if not _is_suhail(interaction):
            await interaction.response.send_message("⛔ Private command.", ephemeral=True)
            return
        actives = await asyncio.to_thread(directives_store.list_active)
        if not actives:
            await interaction.response.send_message("No active directives.", ephemeral=True)
            return
        body = "**Active directives**\n" + "\n".join(
            _format_directive_line(d) for d in actives[:25]
        )
        if len(actives) > 25:
            body += f"\n\n…and {len(actives) - 25} more."
        if len(body) > 1900:
            body = body[:1897] + "..."
        await interaction.response.send_message(body, ephemeral=True)

    @tree.command(
        name="cash-unignore",
        description="Revoke ignore directives for a Discord user.",
    )
    @app_commands.describe(user="The user to unignore")
    async def cash_unignore(interaction: discord.Interaction, user: discord.User):
        if not _is_suhail(interaction):
            await interaction.response.send_message("⛔ Private command.", ephemeral=True)
            return
        target, err = await _resolve_discord_user_to_person(user)
        if err:
            await interaction.response.send_message(err, ephemeral=True)
            return
        active = await asyncio.to_thread(
            directives_store.list_active_for_person, target.person_id,
        )
        revoked = 0
        for d in active:
            if d.action == "ignore":
                if directives_store.revoke(d.directive_id):
                    revoked += 1
        msg = (
            f"Revoked {revoked} ignore directive(s) for **{target.canonical_name}**. "
            f"I'll respond to them again."
            if revoked
            else f"No active ignore directives for **{target.canonical_name}**."
        )
        await interaction.response.send_message(msg, ephemeral=True)

    @tree.command(
        name="cash-forget",
        description="Revoke ALL active directives targeting a Discord user.",
    )
    @app_commands.describe(user="The user to forget all directives for")
    async def cash_forget(interaction: discord.Interaction, user: discord.User):
        if not _is_suhail(interaction):
            await interaction.response.send_message("⛔ Private command.", ephemeral=True)
            return
        target, err = await _resolve_discord_user_to_person(user)
        if err:
            await interaction.response.send_message(err, ephemeral=True)
            return
        active = await asyncio.to_thread(
            directives_store.list_active_for_person, target.person_id,
        )
        revoked = 0
        for d in active:
            if d.target_person_id == target.person_id:
                if directives_store.revoke(d.directive_id):
                    revoked += 1
        msg = (
            f"Revoked {revoked} directive(s) targeting **{target.canonical_name}**."
            if revoked
            else f"No active directives targeting **{target.canonical_name}**."
        )
        await interaction.response.send_message(msg, ephemeral=True)

    logger.info("[discord-commands] registered: /cash-directives, /cash-unignore, /cash-forget")
