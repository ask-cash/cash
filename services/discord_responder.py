"""
discord_responder.py — Fire a proxy reply for a pending mention.

Step 4 scope: LLM-composed reply via services.discord_composer, gated behind
DISCORD_PROXY_ENABLED (default false → dry-run mode that audits but does not
send). Every attempt is appended to user_data/discord_proxy_log.jsonl.

Outcomes (recorded in both queue status and audit log):
  - sent          composer ok, flag on, send succeeded
  - dry-run       composer ok, flag off, deliberately not sent
  - vetoed        composer self-vetoed (sensitive content)
  - send-failed   composer ok, send raised
  - cancelled     owner-active-late-check fired
  - skipped       original deleted / channel unreachable / etc.
"""

import asyncio
import datetime as dt
import json
import logging
import os
from typing import Optional

import discord

from services.availability import (
    AvailabilityReason,
    explain_unavailability,
)
from services.directives import resolve as directives_resolve
from services.directives import store as directives_store
from services.discord_composer import FALLBACK_REPLY, compose_proxy_reply
from services.discord_queue import DiscordQueue, PendingReply
from services.identity import history as identity_history
from services.identity import summaries as identity_summaries

logger = logging.getLogger(__name__)

AUDIT_LOG_PATH = "user_data/discord_proxy_log.jsonl"


def _proxy_enabled() -> bool:
    return os.getenv("DISCORD_PROXY_ENABLED", "false").lower() in ("1", "true", "yes")


def _history_limit() -> int:
    try:
        return max(0, int(os.getenv("DISCORD_PROXY_HISTORY_LIMIT", "10")))
    except ValueError:
        return 10


def _audit(
    record: PendingReply,
    reason: Optional[AvailabilityReason],
    composed: dict,
    outcome: str,
    *,
    extra: Optional[dict] = None,
) -> None:
    entry = {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "outcome": outcome,
        "message_id": record.message_id,
        "channel_id": record.channel_id,
        "guild_id": record.guild_id,
        "asker_id": record.mentioner_id,
        "asker": record.mentioner_name,
        "asker_person_id": record.mentioner_person_id or None,
        "original_message": record.content,
        "availability": (
            {
                "busy": reason.busy,
                "label": reason.label,
                "until": reason.until.isoformat() if reason.until else None,
                "free_after": reason.free_after.isoformat() if reason.free_after else None,
                "working_hours": reason.working_hours,
            }
            if reason is not None
            else None
        ),
        "composed_reply": composed.get("reply"),
        "should_send": composed.get("should_send", True),
        "skip_reason": composed.get("reason_if_skip", ""),
    }
    if extra:
        entry.update(extra)
    try:
        # Tenant-scoped audit trail (services.state_store: Postgres in prod,
        # per-tenant file locally).
        from services import state_store

        state_store.append_event("discord", "proxy_log", entry)
    except Exception:
        logger.exception("[responder] failed to write audit log")


async def _owner_active_in_channel_since(
    client: discord.Client, channel_id: int, owner_id: int, since: dt.datetime
) -> bool:
    """Did Suhail post anything in this channel after `since`? Late safety net."""
    channel = client.get_channel(channel_id)
    if channel is None:
        try:
            channel = await client.fetch_channel(channel_id)
        except Exception:
            logger.exception("Could not fetch channel %s for late-check", channel_id)
            return False
    try:
        async for msg in channel.history(limit=50, after=since):
            if msg.author.id == owner_id:
                return True
    except Exception:
        logger.exception("history() failed for channel %s", channel_id)
    return False


def _build_asker_history(record: PendingReply) -> str:
    """Per-person history for the composer (Step 4 + Step 7).

    Strategy:
      - If a rolling summary exists (Step 7), include it + only the messages
        that arrived AFTER the summary's last_built_at. Bounded prompt size.
      - Otherwise (no summary yet — first ~20 messages with this person),
        fall back to the last 15 raw lines.

    The summary is built daily by `summaries.rebuild_stale`. Until that job
    has run for a person, the raw fallback keeps things working.
    """
    pid = record.mentioner_person_id
    if not pid:
        return ""

    try:
        summary_row = identity_summaries.get_summary_row(pid)
    except Exception:
        logger.exception("[responder] summaries.get_summary_row failed for %s", pid)
        summary_row = None

    parts: list[str] = []

    if summary_row and summary_row.summary_md.strip():
        parts.append(
            "=== Summary of past chats with this person ===\n"
            + summary_row.summary_md.strip()
        )
        # Only messages newer than the summary itself.
        try:
            recent = identity_history.recent_for_person(pid, limit=10, days=30)
        except Exception:
            logger.exception("[responder] history fetch failed for %s", pid)
            recent = []
        post_summary = [
            e for e in recent
            if (e.get("timestamp") or "") > summary_row.last_built_at
        ]
        if post_summary:
            parts.append(
                f"=== Since summary was built ({summary_row.last_built_at[:10]}) ===\n"
                + identity_history.format_for_prompt(post_summary, max_chars=240)
            )
    else:
        # No summary yet — use the last 15 raw lines.
        try:
            entries = identity_history.recent_for_person(pid, limit=15, days=180)
        except Exception:
            logger.exception("[responder] history fetch failed for %s", pid)
            entries = []
        if entries:
            parts.append(
                "=== Recent chat history ===\n"
                + identity_history.format_for_prompt(entries, max_chars=240)
            )

    return "\n\n".join(parts)


async def _fetch_recent_context(original: discord.Message, limit: int) -> list[str]:
    """Up to `limit` messages before the mention, oldest-first, formatted."""
    if limit <= 0:
        return []
    msgs = []
    try:
        async for msg in original.channel.history(before=original, limit=limit):
            msgs.append(msg)
    except Exception:
        logger.exception("[responder] failed to fetch recent context")
        return []
    msgs.reverse()  # discord.py returns newest-first; we want oldest-first
    formatted = []
    for m in msgs:
        body = (m.clean_content or "").strip()
        if not body:
            continue
        if len(body) > 200:
            body = body[:197] + "..."
        formatted.append(f"{m.author.display_name}: {body}")
    return formatted


async def _resolve_directive_for_record(
    record: PendingReply,
) -> directives_resolve.EffectiveAction:
    """Resolve active directives against the queued mention's event.

    Best-effort: any failure (no person_id, DB error) returns the default
    'reply' action so the proxy flow continues normally.
    """
    if not record.mentioner_person_id:
        return directives_resolve.EffectiveAction(action="reply")
    try:
        directives = await asyncio.to_thread(
            directives_store.list_active_for_person, record.mentioner_person_id,
        )
    except Exception:
        logger.exception(
            "[responder] directive lookup failed for person=%s — defaulting to reply",
            record.mentioner_person_id,
        )
        return directives_resolve.EffectiveAction(action="reply")
    event = directives_resolve.Event(
        platform="discord",
        workspace_id=str(record.guild_id) if record.guild_id else None,
        channel_id=str(record.channel_id),
        person_id=record.mentioner_person_id,
    )
    return directives_resolve.effective_action(event, directives)


async def fire_proxy_reply(
    *,
    message_id: int,
    queue: DiscordQueue,
    client: discord.Client,
    owner_id: int,
) -> None:
    """Scheduler job entrypoint. Re-checks state, composes, then sends or audits."""
    record = queue.get(message_id)
    if record is None:
        logger.info("[responder] no record for %s — nothing to fire", message_id)
        return
    if record.status != "pending":
        logger.info("[responder] record %s status=%s — skipping fire", message_id, record.status)
        return

    created_at = dt.datetime.fromisoformat(record.created_at)
    if await _owner_active_in_channel_since(client, record.channel_id, owner_id, created_at):
        await queue.cancel(message_id, "owner-active-late-check")
        return

    # Directive resolution — runs BEFORE we fetch the message or call the LLM.
    # Cheap path for ignore: skip everything, log audit, no API cost.
    action = await _resolve_directive_for_record(record)

    if action.action == "ignore":
        await queue.mark_skipped(
            message_id, f"ignore-directive:{action.chosen_directive_id}",
        )
        _audit(
            record, None,
            {
                "reply": "",
                "should_send": False,
                "reason_if_skip": f"ignore directive {action.chosen_directive_id}",
            },
            outcome="ignored-by-directive",
            extra={"directive_id": action.chosen_directive_id},
        )
        logger.info(
            "[responder] ignored msg=%s per directive=%s",
            message_id, action.chosen_directive_id,
        )
        return

    channel = client.get_channel(record.channel_id)
    if channel is None:
        try:
            channel = await client.fetch_channel(record.channel_id)
        except Exception:
            logger.exception("Could not fetch channel %s to send proxy reply", record.channel_id)
            await queue.mark_skipped(message_id, "channel-unreachable")
            return

    try:
        original = await channel.fetch_message(message_id)
    except discord.NotFound:
        logger.info("[responder] original message %s deleted — skipping", message_id)
        await queue.mark_skipped(message_id, "original-deleted")
        return
    except Exception:
        logger.exception("[responder] fetch_message failed for %s", message_id)
        await queue.mark_skipped(message_id, "fetch-failed")
        return

    if action.action == "auto_reply":
        canned = (action.payload.get("text") or "").strip()
        if canned:
            text = canned[:1900]
            try:
                await original.reply(text)
            except Exception:
                logger.exception("[responder] auto_reply send failed for %s", message_id)
                await queue.mark_skipped(message_id, "send-failed")
                _audit(
                    record, None,
                    {"reply": text, "should_send": True, "reason_if_skip": ""},
                    outcome="send-failed",
                    extra={"directive_id": action.chosen_directive_id},
                )
                return
            await queue.mark_sent(message_id)
            _audit(
                record, None,
                {"reply": text, "should_send": True, "reason_if_skip": ""},
                outcome="auto-replied",
                extra={"directive_id": action.chosen_directive_id},
            )
            logger.info(
                "[responder] auto-replied msg=%s per directive=%s",
                message_id, action.chosen_directive_id,
            )
            return
        logger.warning(
            "[responder] auto_reply directive %s missing payload.text — falling through to composer",
            action.chosen_directive_id,
        )

    try:
        reason = await asyncio.to_thread(explain_unavailability)
    except Exception:
        logger.exception("[responder] availability lookup failed for %s", message_id)
        reason = AvailabilityReason(busy=False, label="probably just away from his desk")

    recent_context = await _fetch_recent_context(original, _history_limit())
    channel_name = getattr(channel, "name", "")
    asker_history = await asyncio.to_thread(_build_asker_history, record)

    composed = await asyncio.to_thread(
        compose_proxy_reply,
        record=record,
        reason=reason,
        recent_context=recent_context,
        channel_name=channel_name,
        asker_history=asker_history,
    )

    if not composed["should_send"]:
        await queue.mark_skipped(message_id, f"vetoed:{composed['reason_if_skip']}")
        _audit(record, reason, composed, outcome="vetoed")
        logger.info(
            "[responder] vetoed proxy reply for %s: %s",
            message_id, composed["reason_if_skip"] or "(no reason given)",
        )
        return

    if not _proxy_enabled():
        await queue.mark_skipped(message_id, "dry-run")
        _audit(record, reason, composed, outcome="dry-run")
        logger.info(
            "[responder] [DRY-RUN] would-send for %s: %s",
            message_id, composed["reply"][:200],
        )
        return

    reply_text = composed["reply"] or FALLBACK_REPLY
    if len(reply_text) > 1900:
        reply_text = reply_text[:1897] + "..."

    try:
        await original.reply(reply_text)
    except Exception:
        logger.exception("[responder] failed to send proxy reply for %s", message_id)
        await queue.mark_skipped(message_id, "send-failed")
        _audit(record, reason, composed, outcome="send-failed")
        return

    await queue.mark_sent(message_id)
    _audit(record, reason, composed, outcome="sent")
    logger.info(
        "[responder] sent proxy reply for %s (busy=%s label=%s)",
        message_id, reason.busy, reason.label,
    )
