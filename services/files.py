"""
files.py — Persistent storage for user-uploaded files.

File bytes live in object storage (services.storage: S3 in prod, local disk in
dev); the searchable index is a tenant-scoped JSON document in
services.state_store. Both are isolated per tenant so uploads never leak
across accounts.
"""

import base64
import os
import uuid
import datetime as dt
from typing import Optional

from services import state_store, storage
from services.user_profile import now as ist_now

# Back-compat: a couple of handlers import this constant.
UPLOADS_DIR = "user_data/uploads"
NAMESPACE = "files"
INDEX_KEY = "index"


def _load_index() -> list[dict]:
    return state_store.read_json(NAMESPACE, INDEX_KEY, default=[])


def _save_index(index: list[dict]):
    state_store.write_json(NAMESPACE, INDEX_KEY, index)


def save_file(
    telegram_file_id: str,
    original_name: str,
    local_path: str,
    mime_type: str = "",
    caption: str = "",
    size_bytes: int = 0,
) -> dict:
    """Upload the file to object storage, register it in the index, return its record."""
    file_id = uuid.uuid4().hex[:12]
    safe_name = os.path.basename(original_name) or "upload"
    key = storage.tenant_key(f"{file_id}_{safe_name}")
    storage.put_file(local_path, key, content_type=mime_type)

    record = {
        "id": file_id,
        "telegram_file_id": telegram_file_id,
        "name": original_name,
        "storage_key": key,
        "mime_type": mime_type,
        "caption": caption,
        "size_bytes": size_bytes,
        "uploaded_at": ist_now().isoformat(),
    }
    index = _load_index()
    index.append(record)
    _save_index(index)
    return record


def list_recent(limit: int = 10) -> list[dict]:
    """Return the most recent uploads, newest first."""
    index = _load_index()
    return list(reversed(index[-limit:]))


def get_latest() -> Optional[dict]:
    """The single most recent upload, if any."""
    index = _load_index()
    return index[-1] if index else None


def find_by_ref(ref: str) -> Optional[dict]:
    """Find a file by id, exact name, or fuzzy substring match on name.

    Falls back to the latest upload when ref is empty.
    """
    index = _load_index()
    if not index:
        return None
    if not ref:
        return index[-1]

    ref_lower = ref.lower().strip()
    for rec in reversed(index):
        if rec["id"] == ref_lower or rec["name"].lower() == ref_lower:
            return rec
    for rec in reversed(index):
        if ref_lower in rec["name"].lower():
            return rec
    return None


def local_path_for(record: dict) -> Optional[str]:
    """Materialize a record's bytes to a local filesystem path (or None)."""
    key = record.get("storage_key")
    if not key:
        # Legacy records may carry a literal local path.
        legacy = record.get("path")
        return legacy if legacy and os.path.exists(legacy) else None
    suffix = os.path.splitext(record.get("name", ""))[1]
    return storage.local_path_for(key, suffix=suffix)


def get_bytes(record: dict) -> Optional[bytes]:
    key = record.get("storage_key")
    if key:
        return storage.get_bytes(key)
    legacy = record.get("path")
    if legacy and os.path.exists(legacy):
        with open(legacy, "rb") as f:
            return f.read()
    return None


def build_claude_content_block(record: dict) -> Optional[dict]:
    """Build a Claude-compatible content block for a stored file.

    - PDFs become a document block (base64).
    - Images become an image block (base64).
    - Text-like files become a plain-text block with the file contents inline.
    - Anything else returns None (caller falls back to a filename-only mention).
    """
    mime = (record.get("mime_type") or "").lower()
    name = record.get("name", "")
    data = get_bytes(record)
    if data is None:
        return None

    if mime == "application/pdf" or name.lower().endswith(".pdf"):
        encoded = base64.standard_b64encode(data).decode("utf-8")
        return {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": encoded},
        }

    if mime.startswith("image/"):
        encoded = base64.standard_b64encode(data).decode("utf-8")
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": mime, "data": encoded},
        }

    if mime.startswith("text/") or mime in {"application/json", "application/xml"} or _looks_like_text(name):
        try:
            text = data.decode("utf-8", errors="replace")
        except Exception:
            return None
        # Cap to ~200k chars to stay well under token limits.
        text = text[:200_000]
        return {"type": "text", "text": f"File: {name}\n\n{text}"}

    return None


def _looks_like_text(name: str) -> bool:
    ext = os.path.splitext(name)[1].lower().lstrip(".")
    return ext in {
        "txt", "md", "csv", "tsv", "log", "json", "yaml", "yml", "xml",
        "py", "js", "ts", "tsx", "jsx", "html", "css", "sh", "sql", "toml", "ini",
    }


def build_files_context(limit: int = 5) -> str:
    """Compact summary of recent uploads for injection into Claude's context."""
    recent = list_recent(limit=limit)
    if not recent:
        return "No files uploaded yet."
    lines = []
    for rec in recent:
        uploaded = rec.get("uploaded_at", "")[:16].replace("T", " ")
        caption = f" — caption: {rec['caption']}" if rec.get("caption") else ""
        lines.append(
            f"  [{rec['id']}] {rec['name']} ({rec.get('mime_type', '?')}, "
            f"uploaded {uploaded}){caption}"
        )
    return "\n".join(lines)
