"""
backfill_identities.py — One-shot: populate the identity tables from existing
memory and authoritative env config.

What it does:
  1. Pre-link Suhail's known platform identities (from .env) to one canonical
     person, with the operator name as canonical_name. Telegram and Discord
     today; trivially extensible to Slack/Teams later.
  2. Walk user_data/memory/conversations.jsonl. For every Discord author
     observed, resolve() a person + platform_identity row. Idempotent:
     repeat sightings just refresh display_name and last_seen.

Usage:
    ./venv/bin/python scripts/backfill_identities.py

Idempotent. Safe to re-run after every memory file update.
"""

import json
import logging
import os
import sys
from collections import Counter
from typing import Optional

from dotenv import load_dotenv

# Make sibling `services/` importable when run as a script from repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.identity import (  # noqa: E402
    link_platform_identity,
    list_platform_identities_for_person,
    resolve,
    set_canonical_name,
)
from services.identity.store import DB_PATH, connect  # noqa: E402

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

MEM_PATH = os.path.join("user_data", "memory", "conversations.jsonl")


def _ensure_owner_person() -> Optional[str]:
    """Pre-link Suhail's known platform identities under one canonical person."""
    tg_id = (os.getenv("YOUR_TELEGRAM_USER_ID") or "").strip()
    discord_id = (os.getenv("DISCORD_OWNER_USER_ID") or os.getenv("DISCORD_SUHAIL_USER_ID") or "").strip()
    canonical_name = (os.getenv("USER_NAME") or "Suhail").strip()

    if (not tg_id or tg_id == "0") and (not discord_id or discord_id == "0"):
        logger.info("owner: env config not present (YOUR_TELEGRAM_USER_ID / "
                    "DISCORD_OWNER_USER_ID); skipping pre-link")
        return None

    person_id: Optional[str] = None

    if tg_id and tg_id != "0":
        person_id = resolve(
            platform="telegram", platform_user_id=tg_id,
            display_name=canonical_name,
        )

    if discord_id and discord_id != "0":
        if person_id is None:
            person_id = resolve(
                platform="discord", platform_user_id=discord_id,
                display_name=canonical_name,
            )
        else:
            link_platform_identity(
                person_id=person_id, platform="discord",
                platform_user_id=discord_id, display_name=canonical_name,
            )

    if person_id:
        set_canonical_name(person_id, canonical_name)

    return person_id


def _read_log_entries(path: str):
    if not os.path.exists(path):
        logger.info("memory log not found at %s — nothing to walk", path)
        return
    with open(path) as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                yield json.loads(raw)
            except json.JSONDecodeError:
                continue


def _walk_discord_authors():
    """Yield unique-by-author dicts from conversations.jsonl. Skips Cash's own outputs."""
    for entry in _read_log_entries(MEM_PATH):
        if entry.get("role") != "user":
            continue
        md = entry.get("metadata") or {}
        if md.get("surface") != "discord":
            continue
        author_id = md.get("author_id")
        if not author_id:
            continue
        yield {
            "platform_user_id": str(author_id),
            "display_name": md.get("author_name") or md.get("asker"),
            "handle": md.get("asker_handle"),
            "workspace_id": str(md.get("guild_id")) if md.get("guild_id") else None,
        }


def _summarize() -> dict:
    with connect() as conn:
        people_count = conn.execute("SELECT COUNT(*) FROM people").fetchone()[0]
        pi_rows = conn.execute(
            "SELECT platform, COUNT(*) FROM platform_identities GROUP BY platform"
        ).fetchall()
    return {
        "people": people_count,
        "platform_identities": {row[0]: row[1] for row in pi_rows},
    }


def main() -> int:
    suhail = _ensure_owner_person()
    if suhail:
        ids = list_platform_identities_for_person(suhail)
        plats = ", ".join(sorted({i.platform for i in ids}))
        logger.info("Suhail: %s linked across [%s]", suhail, plats)
    else:
        logger.info("Suhail: no env config — pre-link skipped")

    counter = Counter()
    seen_keys: set[tuple[str, str]] = set()

    for author in _walk_discord_authors():
        key = ("discord", author["platform_user_id"])
        if key in seen_keys:
            counter["seen-again"] += 1
            continue
        seen_keys.add(key)
        try:
            resolve(
                platform="discord",
                platform_user_id=author["platform_user_id"],
                workspace_id=author["workspace_id"],
                display_name=author["display_name"],
                handle=author["handle"],
            )
            counter["resolved"] += 1
        except Exception as e:
            logger.warning("failed for discord/%s: %s", author["platform_user_id"], e)
            counter["failed"] += 1

    logger.info("")
    logger.info("Backfill summary:")
    logger.info("  unique authors processed : %d", counter["resolved"])
    logger.info("  duplicates skipped       : %d", counter["seen-again"])
    logger.info("  failures                 : %d", counter["failed"])
    summary = _summarize()
    logger.info("  total people in DB       : %d", summary["people"])
    logger.info("  total platform identities: %s", summary["platform_identities"])
    logger.info("")
    logger.info("Inspect with:  sqlite3 %s 'SELECT * FROM people'", DB_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
