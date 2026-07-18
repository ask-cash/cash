"""Tenant-scoped dashboard attachment metadata, validation, and model blocks."""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import os
import re
import uuid
from pathlib import Path
from typing import Iterable, Optional

from services import dispatch_outbox
from services import storage
from services.chat_runtime import conversation_lock
from services.db import connect
from services.tenancy import current_tenant_id

_TEXT_EXTENSIONS = {
    ".txt", ".md", ".csv", ".tsv", ".log", ".json", ".yaml", ".yml",
    ".xml", ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".sh",
    ".sql", ".toml", ".ini",
}
_MIME_TYPES = (
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
    "application/xml",
    "audio/mpeg",
    "audio/mp4",
    "audio/wav",
    "audio/x-wav",
    "audio/ogg",
    "audio/webm",
    "video/mp4",
    "video/webm",
)
_AUDIO_VIDEO_PREFIXES = ("audio/", "video/")
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._()\- ]+")
_MEDIA_JOB_TYPE = "media_transcription"


class AttachmentError(ValueError):
    def __init__(self, message: str, *, code: str = "invalid_attachment", status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def _positive_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def max_files_per_message() -> int:
    return _positive_int("CHAT_MAX_ATTACHMENTS", 4)


def max_file_bytes(plan: str = "free") -> int:
    default = 10 * 1024 * 1024 if (plan or "free").lower() == "free" else 20 * 1024 * 1024
    return _positive_int("CHAT_MAX_ATTACHMENT_BYTES", default)


def max_total_bytes_per_message(plan: str = "free") -> int:
    default = 20 * 1024 * 1024 if (plan or "free").lower() == "free" else 50 * 1024 * 1024
    return _positive_int("CHAT_MAX_MESSAGE_ATTACHMENT_BYTES", default)


def max_tenant_storage_bytes(plan: str = "free") -> int:
    default = 100 * 1024 * 1024 if (plan or "free").lower() == "free" else 2 * 1024**3
    return _positive_int("CHAT_TENANT_STORAGE_BYTES", default)


def max_provider_image_bytes() -> int:
    return _positive_int(
        "CHAT_MAX_PROVIDER_IMAGE_BYTES",
        7 * 1024 * 1024,
    )


def max_pdf_pages(plan: str = "free") -> int:
    if (plan or "free").lower() == "free":
        return _positive_int("FREE_CHAT_MAX_PDF_PAGES", 15)
    return _positive_int("PRO_CHAT_MAX_PDF_PAGES", 100)


def accepted_mime_types() -> tuple[str, ...]:
    return _MIME_TYPES


def accepted_client_types() -> tuple[str, ...]:
    """MIME types plus extensions browsers often report with an empty MIME."""
    return _MIME_TYPES + tuple(sorted(_TEXT_EXTENSIONS))


def is_audio_or_video(mime_type: str) -> bool:
    return (mime_type or "").lower().startswith(_AUDIO_VIDEO_PREFIXES)


def safe_filename(name: str) -> str:
    base = Path(name or "upload").name.replace("\x00", "").strip() or "upload"
    cleaned = _SAFE_FILENAME_RE.sub("_", base)
    return cleaned[:160] or "upload"


def _looks_text(sample: bytes) -> bool:
    if b"\x00" in sample:
        return False
    if not sample:
        return True
    try:
        sample.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def detect_mime(sample: bytes, filename: str, declared: str = "") -> str:
    """Small, dependency-free magic-byte detector for the supported allowlist."""
    lowered = filename.lower()
    declared = (declared or "").split(";")[0].strip().lower()
    if sample.startswith(b"%PDF-"):
        return "application/pdf"
    if sample.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if sample.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if sample.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(sample) >= 12 and sample[:4] == b"RIFF" and sample[8:12] == b"WEBP":
        return "image/webp"
    if len(sample) >= 12 and sample[:4] == b"RIFF" and sample[8:12] == b"WAVE":
        return "audio/wav"
    if sample.startswith(b"OggS"):
        return "audio/ogg"
    if sample.startswith(b"ID3") or (len(sample) > 1 and sample[0] == 0xFF and sample[1] & 0xE0 == 0xE0):
        return "audio/mpeg"
    if sample.startswith(b"\x1aE\xdf\xa3"):
        return "audio/webm" if declared.startswith("audio/") else "video/webm"
    if len(sample) >= 12 and sample[4:8] == b"ftyp":
        return "audio/mp4" if declared.startswith("audio/") else "video/mp4"

    extension = Path(lowered).suffix
    if extension in _TEXT_EXTENSIONS and _looks_text(sample):
        mapping = {
            ".md": "text/markdown",
            ".csv": "text/csv",
            ".json": "application/json",
            ".xml": "application/xml",
        }
        return mapping.get(extension, "text/plain")
    if declared in {"text/plain", "text/markdown", "text/csv", "application/json", "application/xml"} and _looks_text(sample):
        return declared
    raise AttachmentError(
        "That file type isn’t supported. Attach a PDF, image, text/code file, or supported audio/video file.",
        code="unsupported_file_type",
        status_code=415,
    )


def inspect_path(
    path: str,
    *,
    filename: str,
    declared_mime: str = "",
    plan: str = "free",
) -> tuple[str, int, str]:
    size = os.path.getsize(path)
    if size <= 0:
        raise AttachmentError("The selected file is empty.", code="empty_file")
    if size > max_file_bytes(plan):
        limit_mb = max_file_bytes(plan) // (1024 * 1024)
        raise AttachmentError(
            f"Files can be up to {limit_mb} MB on your current plan.",
            code="file_too_large",
            status_code=413,
        )
    with open(path, "rb") as source:
        sample = source.read(8192)
        digest = hashlib.sha256()
        digest.update(sample)
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    mime = detect_mime(sample, filename, declared_mime)
    if mime.startswith("image/"):
        # Direct Claude API images are capped after base64 encoding. Seven MiB
        # raw stays comfortably below the current ten-MiB encoded limit.
        image_limit = max_provider_image_bytes()
        if size > image_limit:
            raise AttachmentError(
                "Images can be up to 7 MB.",
                code="provider_image_too_large",
                status_code=413,
            )
        try:
            from PIL import Image, UnidentifiedImageError

            with Image.open(path) as image:
                width, height = image.size
                image.verify()
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise AttachmentError(
                "That image is damaged or unsupported.",
                code="invalid_image",
                status_code=415,
            ) from exc
        max_edge = _positive_int("CHAT_MAX_IMAGE_EDGE_PIXELS", 8_000)
        if width <= 0 or height <= 0 or width > max_edge or height > max_edge:
            raise AttachmentError(
                f"Images must be no larger than {max_edge} × {max_edge} pixels.",
                code="image_dimensions_exceeded",
                status_code=413,
            )
    elif mime == "application/pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(path, strict=False)
            if reader.is_encrypted:
                raise AttachmentError(
                    "Password-protected PDFs aren’t supported.",
                    code="encrypted_pdf",
                    status_code=415,
                )
            page_count = len(reader.pages)
        except AttachmentError:
            raise
        except Exception as exc:
            raise AttachmentError(
                "That PDF is damaged or unsupported.",
                code="invalid_pdf",
                status_code=415,
            ) from exc
        max_pages = max_pdf_pages(plan)
        if page_count <= 0 or page_count > max_pages:
            raise AttachmentError(
                f"PDFs can contain up to {max_pages} pages.",
                code="pdf_page_limit_exceeded",
                status_code=413,
            )
    return mime, size, digest.hexdigest()


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _new_id() -> str:
    return f"att_{uuid.uuid4().hex[:24]}"


def _row_view(row, *, include_private: bool = False) -> dict:
    record = {
        "id": row["id"],
        "conversationId": row["conversation_id"],
        "messageId": row["message_id"],
        "name": row["original_name"],
        "mimeType": row["mime_type"],
        "sizeBytes": int(row["size_bytes"]),
        "status": row["status"],
        "createdAt": row["created_at"],
        "previewUrl": f"/api/attachments/{row['id']}",
    }
    if include_private:
        record.update({
            "storage_key": row["storage_key"],
            "mime_type": row["mime_type"],
            "size_bytes": int(row["size_bytes"]),
            "original_name": row["original_name"],
            "checksum": row["checksum"],
            "transcript": row["transcript"] if "transcript" in row.keys() else None,
        })
    return record


def tenant_storage_used() -> int:
    tid = current_tenant_id()
    with connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(size_bytes), 0) AS used FROM attachments "
            "WHERE tenant_id = ? AND deleted_at IS NULL",
            (tid,),
        ).fetchone()
    return int(row["used"] if row else 0)


def create_from_path(
    conversation_id: str,
    path: str,
    *,
    original_name: str,
    declared_mime: str = "",
    plan: str = "free",
) -> dict:
    tid = current_tenant_id()
    mime, size, checksum = inspect_path(
        path,
        filename=original_name,
        declared_mime=declared_mime,
        plan=plan,
    )
    if is_audio_or_video(mime):
        from services import transcription

        if not transcription.is_configured():
            raise AttachmentError(
                "Audio and video analysis is not configured on this deployment.",
                code="transcription_not_configured",
                status_code=503,
            )
    # Share the conversation lock with send/delete so a conversation cannot
    # disappear after the existence check but before its attachment row lands.
    with conversation_lock(tid, conversation_id):
        with connect() as conn:
            conv = conn.execute(
                "SELECT id FROM conversations WHERE tenant_id = ? AND id = ?",
                (tid, conversation_id),
            ).fetchone()
        if conv is None:
            raise AttachmentError(
                "Conversation not found.",
                code="conversation_not_found",
                status_code=404,
            )

        # The tenant-wide lock makes the quota check and reservation serial
        # across uploads to different conversations.
        with conversation_lock(tid, "attachment-storage"):
            if tenant_storage_used() + size > max_tenant_storage_bytes(plan):
                raise AttachmentError(
                    "Your attachment storage allowance is full. "
                    "Remove older files or upgrade your plan.",
                    code="storage_quota_exceeded",
                    status_code=413,
                )

            attachment_id = _new_id()
            name = safe_filename(original_name)
            key = storage.tenant_key(f"dashboard/{attachment_id}/{name}")
            storage.put_file(path, key, content_type=mime)
            now = _now_iso()
            status = "processing" if is_audio_or_video(mime) else "ready"
            try:
                with connect() as conn:
                    conn.execute(
                        """
                        INSERT INTO attachments
                            (tenant_id, id, conversation_id, message_id, original_name,
                             storage_key, mime_type, size_bytes, checksum, transcript,
                             status, created_at, deleted_at)
                        VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, NULL, ?, ?, NULL)
                        """,
                        (tid, attachment_id, conversation_id, name, key, mime, size,
                         checksum, status, now),
                    )
                    if is_audio_or_video(mime):
                        dispatch_outbox.add(
                            conn,
                            dispatch_id=f"media:{tid}:{attachment_id}",
                            tenant_id=tid,
                            job_type=_MEDIA_JOB_TYPE,
                            resource_id=attachment_id,
                            payload={"attachment_id": attachment_id},
                            created_at=now,
                        )
            except Exception:
                storage.delete(key)
                raise

    record = get_attachment(attachment_id, include_private=True)
    if record is None:  # pragma: no cover - defensive after successful insert
        raise AttachmentError("The attachment could not be saved.")
    return record


def get_attachment(attachment_id: str, *, include_private: bool = False) -> Optional[dict]:
    tid = current_tenant_id()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM attachments WHERE tenant_id = ? AND id = ? AND deleted_at IS NULL",
            (tid, attachment_id),
        ).fetchone()
    return _row_view(row, include_private=include_private) if row else None


def list_for_conversation(conversation_id: str) -> list[dict]:
    tid = current_tenant_id()
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM attachments WHERE tenant_id = ? AND conversation_id = ? "
            "AND deleted_at IS NULL ORDER BY created_at ASC, id ASC",
            (tid, conversation_id),
        ).fetchall()
    return [_row_view(row) for row in rows]


def pending_transcriptions(limit: int = 50) -> list[dict]:
    """Return durable media work that still needs a transcript."""
    tid = current_tenant_id()
    limit = min(max(int(limit), 1), 200)
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM attachments "
            "WHERE tenant_id = ? AND status = 'processing' "
            "AND deleted_at IS NULL "
            "ORDER BY created_at ASC, id ASC LIMIT ?",
            (tid, limit),
        ).fetchall()
    return [_row_view(row, include_private=True) for row in rows]


def mark_transcription_enqueued(attachment_id: str) -> None:
    tid = current_tenant_id()
    dispatch_outbox.mark_delivered(
        f"media:{tid}:{attachment_id}",
        _now_iso(),
    )


def resolve_for_message(
    conversation_id: str,
    attachment_ids: Iterable[str],
    *,
    plan: str = "free",
) -> list[dict]:
    ids = list(dict.fromkeys(a for a in attachment_ids if a))
    if len(ids) > max_files_per_message():
        raise AttachmentError(
            f"Attach up to {max_files_per_message()} files per message.",
            code="too_many_files",
        )
    if not ids:
        return []
    tid = current_tenant_id()
    placeholders = ",".join("?" for _ in ids)
    with connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM attachments WHERE tenant_id = ? AND conversation_id = ? "
            f"AND id IN ({placeholders}) AND deleted_at IS NULL",
            (tid, conversation_id, *ids),
        ).fetchall()
    by_id = {row["id"]: row for row in rows}
    if len(by_id) != len(ids):
        raise AttachmentError(
            "One or more attachments do not belong to this conversation.",
            code="attachment_not_found",
            status_code=404,
        )
    records = [_row_view(by_id[attachment_id], include_private=True) for attachment_id in ids]
    if sum(int(record.get("sizeBytes") or 0) for record in records) > max_total_bytes_per_message(plan):
        raise AttachmentError(
            "Those attachments are too large to send together.",
            code="attachment_total_too_large",
            status_code=413,
        )
    for record in records:
        if record["messageId"]:
            raise AttachmentError("An attachment can only be sent once.", code="attachment_already_sent")
        if record["status"] != "ready":
            raise AttachmentError(
                f"{record['name']} is not ready yet.",
                code="attachment_not_ready",
                status_code=409,
            )
    return records


def link_to_message(attachment_ids: Iterable[str], message_id: str) -> None:
    ids = list(dict.fromkeys(a for a in attachment_ids if a))
    if not ids:
        return
    tid = current_tenant_id()
    placeholders = ",".join("?" for _ in ids)
    with connect() as conn:
        message = conn.execute(
            "SELECT conversation_id FROM conversation_messages "
            "WHERE tenant_id = ? AND id = ?",
            (tid, message_id),
        ).fetchone()
        if message is None:
            raise AttachmentError(
                "The message no longer exists.",
                code="message_not_found",
                status_code=404,
            )
        claimed = conn.execute(
            f"UPDATE attachments SET message_id = ? WHERE tenant_id = ? "
            f"AND conversation_id = ? AND id IN ({placeholders}) "
            f"AND message_id IS NULL AND status = 'ready' AND deleted_at IS NULL",
            (message_id, tid, message["conversation_id"], *ids),
        )
        if int(getattr(claimed, "rowcount", 0) or 0) != len(ids):
            raise AttachmentError(
                "One or more attachments changed before they could be sent. "
                "Review the draft and try again.",
                code="attachment_claim_conflict",
                status_code=409,
            )


def unlink_from_message(message_id: str) -> None:
    tid = current_tenant_id()
    with connect() as conn:
        conn.execute(
            "UPDATE attachments SET message_id = NULL WHERE tenant_id = ? AND message_id = ?",
            (tid, message_id),
        )


def set_transcript(attachment_id: str, transcript: str, *, status: str = "ready") -> dict:
    tid = current_tenant_id()
    with connect() as conn:
        conn.execute(
            "UPDATE attachments SET transcript = ?, status = ? WHERE tenant_id = ? AND id = ?",
            ((transcript or "").strip(), status, tid, attachment_id),
        )
    record = get_attachment(attachment_id, include_private=True)
    if record is None:
        raise AttachmentError("Attachment not found.", status_code=404)
    return record


def set_failed(attachment_id: str) -> None:
    tid = current_tenant_id()
    with connect() as conn:
        conn.execute(
            "UPDATE attachments SET status = 'failed' WHERE tenant_id = ? AND id = ?",
            (tid, attachment_id),
        )


def _delete_conversation_attachments_unlocked(conversation_id: str) -> None:
    tid = current_tenant_id()
    with connect() as conn:
        conn.execute(
            "DELETE FROM dispatch_outbox WHERE tenant_id = ? "
            "AND job_type = ? AND resource_id IN "
            "(SELECT id FROM attachments WHERE tenant_id = ? "
            "AND conversation_id = ?)",
            (tid, _MEDIA_JOB_TYPE, tid, conversation_id),
        )
        rows = conn.execute(
            "SELECT storage_key FROM attachments "
            "WHERE tenant_id = ? AND conversation_id = ?",
            (tid, conversation_id),
        ).fetchall()
        conn.execute(
            "DELETE FROM attachments WHERE tenant_id = ? AND conversation_id = ?",
            (tid, conversation_id),
        )
    for row in rows:
        storage.delete(row["storage_key"])


def delete_conversation_attachments(
    conversation_id: str,
    *,
    lock_held: bool = False,
) -> None:
    """Delete every attachment in a conversation without racing a send/upload.

    ``lock_held`` is reserved for :func:`conversations.delete_conversation`,
    which already owns this exact lock while deleting the remaining child rows.
    """
    tid = current_tenant_id()
    if lock_held:
        _delete_conversation_attachments_unlocked(conversation_id)
        return
    with conversation_lock(tid, conversation_id):
        _delete_conversation_attachments_unlocked(conversation_id)


def delete_attachment(attachment_id: str) -> bool:
    record = get_attachment(attachment_id, include_private=True)
    if record is None:
        return False
    tid = current_tenant_id()
    conversation_id = record["conversationId"]
    with conversation_lock(tid, conversation_id):
        # Re-read after locking: send() may have claimed the attachment between
        # the first lookup (needed to discover the lock key) and lock acquisition.
        with connect() as conn:
            row = conn.execute(
                "SELECT * FROM attachments "
                "WHERE tenant_id = ? AND id = ? AND deleted_at IS NULL",
                (tid, attachment_id),
            ).fetchone()
            if row is None:
                return False
            if row["message_id"]:
                raise AttachmentError(
                    "Sent attachments cannot be removed from a message.",
                    code="attachment_already_sent",
                    status_code=409,
                )
            deleted = conn.execute(
                "DELETE FROM attachments WHERE tenant_id = ? AND id = ? "
                "AND conversation_id = ? AND message_id IS NULL",
                (tid, attachment_id, conversation_id),
            )
            if int(getattr(deleted, "rowcount", 0) or 0) != 1:
                raise AttachmentError(
                    "That attachment changed before it could be removed.",
                    code="attachment_delete_conflict",
                    status_code=409,
                )
            dispatch_outbox.remove(
                conn,
                tenant_id=tid,
                job_type=_MEDIA_JOB_TYPE,
                resource_id=attachment_id,
            )
            storage_key = row["storage_key"]
        storage.delete(storage_key)
        return True


def get_bytes(record: dict) -> Optional[bytes]:
    key = record.get("storage_key")
    return storage.get_bytes(key) if key else None


def build_claude_content_block(record: dict) -> Optional[dict]:
    mime = (record.get("mimeType") or record.get("mime_type") or "").lower()
    transcript = (record.get("transcript") or "").strip()
    if transcript:
        return {
            "type": "text",
            "text": f"Transcript of {record.get('name', 'media')}:\n\n{transcript[:80_000]}",
        }
    data = get_bytes(record)
    if data is None:
        return None
    if mime == "application/pdf":
        return {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": mime,
                "data": base64.standard_b64encode(data).decode("ascii"),
            },
        }
    if mime.startswith("image/"):
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime,
                "data": base64.standard_b64encode(data).decode("ascii"),
            },
        }
    if mime.startswith("text/") or mime in {"application/json", "application/xml"}:
        text = data.decode("utf-8", errors="replace")[:200_000]
        return {"type": "text", "text": f"File: {record.get('name')}\n\n{text}"}
    return None
