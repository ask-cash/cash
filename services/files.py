"""
files.py — Persistent storage for user-uploaded files.

Stores uploaded files under user_data/uploads/ and maintains an index in
user_data/files.json so Cash can recall them in later conversations.
"""

import base64
import json
import os
import uuid
import datetime as dt
from typing import Optional

from services.user_profile import now as ist_now

UPLOADS_DIR = "user_data/uploads"
INDEX_PATH = "user_data/files.json"


def _ensure_dir():
    os.makedirs(UPLOADS_DIR, exist_ok=True)


def _load_index() -> list[dict]:
    if not os.path.exists(INDEX_PATH):
        return []
    try:
        with open(INDEX_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_index(index: list[dict]):
    os.makedirs(os.path.dirname(INDEX_PATH), exist_ok=True)
    with open(INDEX_PATH, "w") as f:
        json.dump(index, f, indent=2)


def save_file(
    telegram_file_id: str,
    original_name: str,
    local_path: str,
    mime_type: str = "",
    caption: str = "",
    size_bytes: int = 0,
) -> dict:
    """Register an uploaded file in the index and return its record."""
    _ensure_dir()
    record = {
        "id": uuid.uuid4().hex[:12],
        "telegram_file_id": telegram_file_id,
        "name": original_name,
        "path": local_path,
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


def build_claude_content_block(record: dict) -> Optional[dict]:
    """Build a Claude-compatible content block for a stored file.

    - PDFs become a document block (base64).
    - Images become an image block (base64).
    - Text-like files become a plain-text block with the file contents inline.
    - Anything else returns None (caller should fall back to a filename-only mention).
    """
    path = record.get("path", "")
    mime = (record.get("mime_type") or "").lower()
    if not path or not os.path.exists(path):
        return None

    if mime == "application/pdf" or path.lower().endswith(".pdf"):
        with open(path, "rb") as f:
            data = base64.standard_b64encode(f.read()).decode("utf-8")
        return {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": data},
        }

    if mime.startswith("image/"):
        with open(path, "rb") as f:
            data = base64.standard_b64encode(f.read()).decode("utf-8")
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": mime, "data": data},
        }

    if mime.startswith("text/") or mime in {"application/json", "application/xml"} or _looks_like_text(path):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            return None
        # Cap to ~200k chars to stay well under token limits.
        text = text[:200_000]
        return {"type": "text", "text": f"File: {record.get('name')}\n\n{text}"}

    return None


def _looks_like_text(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower().lstrip(".")
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
