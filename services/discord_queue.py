"""
discord_queue.py — Persistent pending-reply queue for Suhail mentions.

Each record represents: "Suhail was mentioned at time T in channel C; fire a
proxy reply at fire_at unless cancelled first." Records are stored in
user_data/discord_pending.json.

Single-process consumer: the discord client is the only writer. An
asyncio.Lock serialises mutations within that process so persistence stays
consistent even with concurrent event handlers.
"""

import asyncio
import datetime as dt
import json
import logging
import os
from dataclasses import asdict, dataclass
from typing import Optional

logger = logging.getLogger(__name__)

QUEUE_PATH = "user_data/discord_pending.json"

# If a record's fire_at is older than this on boot, drop it instead of firing
# late — the conversation has moved on.
STALE_FIRE_GRACE_SECONDS = 2 * 60 * 60


@dataclass
class PendingReply:
    message_id: int
    channel_id: int
    guild_id: Optional[int]
    mentioner_id: int
    mentioner_name: str
    content: str
    created_at: str   # ISO8601 UTC
    fire_at: str      # ISO8601 UTC
    status: str = "pending"  # pending | cancelled | sent | skipped
    cancel_reason: Optional[str] = None


class DiscordQueue:
    def __init__(self, path: str = QUEUE_PATH):
        self.path = path
        self._lock = asyncio.Lock()
        self._records: dict[int, PendingReply] = {}

    def load(self) -> None:
        if not os.path.exists(self.path):
            self._records = {}
            return
        try:
            with open(self.path, "r") as f:
                raw = json.load(f)
            self._records = {int(k): PendingReply(**v) for k, v in raw.items()}
            logger.info("Loaded %d discord queue records (%d pending)",
                        len(self._records), len(self.pending()))
        except Exception:
            logger.exception("Failed to load discord queue, starting empty")
            self._records = {}

    def _persist_locked(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(
                {str(k): asdict(v) for k, v in self._records.items()},
                f, indent=2,
            )
        os.replace(tmp, self.path)

    async def enqueue(self, record: PendingReply) -> None:
        async with self._lock:
            self._records[record.message_id] = record
            self._persist_locked()
        logger.info(
            "[queue] enqueued msg=%s channel=%s fire_at=%s",
            record.message_id, record.channel_id, record.fire_at,
        )

    async def cancel(self, message_id: int, reason: str) -> Optional[PendingReply]:
        async with self._lock:
            r = self._records.get(message_id)
            if not r or r.status != "pending":
                return None
            r.status = "cancelled"
            r.cancel_reason = reason
            self._persist_locked()
        logger.info("[queue] cancelled msg=%s reason=%s", message_id, reason)
        return r

    async def cancel_in_channel_before(
        self, channel_id: int, before: dt.datetime, reason: str
    ) -> list[PendingReply]:
        """Cancel pending records in `channel_id` whose mention happened at-or-before `before`.

        Used when Suhail himself posts in a channel — any earlier-than-this-post
        pending mention is now considered "seen" and should not trigger a proxy.
        """
        cancelled: list[PendingReply] = []
        async with self._lock:
            for r in self._records.values():
                if r.status != "pending" or r.channel_id != channel_id:
                    continue
                if dt.datetime.fromisoformat(r.created_at) <= before:
                    r.status = "cancelled"
                    r.cancel_reason = reason
                    cancelled.append(r)
            if cancelled:
                self._persist_locked()
        for r in cancelled:
            logger.info("[queue] cancelled msg=%s reason=%s", r.message_id, reason)
        return cancelled

    async def mark_sent(self, message_id: int) -> None:
        async with self._lock:
            r = self._records.get(message_id)
            if r:
                r.status = "sent"
                self._persist_locked()

    async def mark_skipped(self, message_id: int, reason: str) -> None:
        async with self._lock:
            r = self._records.get(message_id)
            if r:
                r.status = "skipped"
                r.cancel_reason = reason
                self._persist_locked()
        logger.info("[queue] skipped msg=%s reason=%s", message_id, reason)

    def get(self, message_id: int) -> Optional[PendingReply]:
        return self._records.get(message_id)

    def pending(self) -> list[PendingReply]:
        return [r for r in self._records.values() if r.status == "pending"]
