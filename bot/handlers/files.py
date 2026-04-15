"""
files.py — Telegram handler for document/photo uploads.

Saves the uploaded file to disk, records metadata, and acknowledges the user.
Follow-up actions (summarise, attach to event, resend) are driven by the
natural-language handler in bot/handlers/messages.py.
"""

import logging
import os
import re

from telegram import Update
from telegram.ext import ContextTypes

from services.files import save_file, UPLOADS_DIR
from services.memory import log_message

logger = logging.getLogger(__name__)

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(name: str) -> str:
    cleaned = _SAFE_NAME.sub("_", name).strip("._") or "upload"
    return cleaned[:120]


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive a Telegram document or photo, persist it, ack the user."""
    msg = update.message
    if not msg:
        return

    tg_file = None
    original_name = ""
    mime_type = ""
    size_bytes = 0

    if msg.document:
        doc = msg.document
        tg_file = await doc.get_file()
        original_name = doc.file_name or f"document_{doc.file_unique_id}"
        mime_type = doc.mime_type or ""
        size_bytes = doc.file_size or 0
    elif msg.photo:
        photo = msg.photo[-1]  # highest-resolution variant
        tg_file = await photo.get_file()
        original_name = f"photo_{photo.file_unique_id}.jpg"
        mime_type = "image/jpeg"
        size_bytes = photo.file_size or 0
    else:
        return

    os.makedirs(UPLOADS_DIR, exist_ok=True)
    safe_name = _safe_filename(original_name)
    local_path = os.path.join(UPLOADS_DIR, f"{tg_file.file_unique_id}_{safe_name}")

    try:
        await tg_file.download_to_drive(custom_path=local_path)
    except Exception as e:
        logger.error("Failed to download upload '%s': %s", original_name, e)
        await msg.reply_text(f"😿 Couldn't save that file: {e}")
        return

    caption = (msg.caption or "").strip()
    record = save_file(
        telegram_file_id=tg_file.file_id,
        original_name=original_name,
        local_path=local_path,
        mime_type=mime_type,
        caption=caption,
        size_bytes=size_bytes,
    )

    log_message(
        "user",
        f"[uploaded file: {record['name']}]" + (f" caption: {caption}" if caption else ""),
        metadata={"file_id": record["id"], "mime_type": mime_type},
    )

    ack = (
        f"📎 Got it — saved '{record['name']}' (id `{record['id']}`). "
        f"Ask me to summarise it, attach it to a calendar event, or send it back whenever you need."
    )
    await msg.reply_text(ack, parse_mode="Markdown")
    log_message("assistant", ack)
