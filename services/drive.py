"""
drive.py — Minimal Google Drive helper for uploading files the bot creates
and generating shareable links for use as calendar attachments.

Scope used: drive.file (only touches files the app itself creates).
"""

import logging
import os
from typing import Optional

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from calendars.google_calendar import SCOPES

logger = logging.getLogger(__name__)


def _get_drive_service():
    """Build a Drive service from the same token.json the calendar uses."""
    token_path = os.getenv("GOOGLE_TOKEN_PATH", "token.json")
    if not os.path.exists(token_path):
        raise RuntimeError("No token.json — run /connect_google first")
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return build("drive", "v3", credentials=creds)


def upload_and_share(local_path: str, filename: str, mime_type: str = "") -> Optional[dict]:
    """Upload a file to Drive, make it readable by anyone with the link, return metadata.

    Returns a dict with: id, name, mimeType, webViewLink — or None on failure.
    """
    if not os.path.exists(local_path):
        logger.error("upload_and_share: path does not exist — %s", local_path)
        return None

    try:
        drive = _get_drive_service()
    except Exception as e:
        logger.error("Could not build Drive service: %s", e)
        return None

    try:
        media = MediaFileUpload(local_path, mimetype=mime_type or None, resumable=False)
        file = drive.files().create(
            body={"name": filename},
            media_body=media,
            fields="id, name, mimeType, webViewLink",
        ).execute()
        logger.info("Uploaded '%s' to Drive as id=%s", filename, file.get("id"))
    except Exception as e:
        logger.error("Drive upload failed for '%s': %s", filename, e)
        return None

    try:
        drive.permissions().create(
            fileId=file["id"],
            body={"type": "anyone", "role": "reader"},
            fields="id",
        ).execute()
    except Exception as e:
        logger.warning("Could not set anyone-with-link permission on '%s': %s", filename, e)

    return file


def shorten_url(long_url: str) -> str:
    """Shorten a URL via TinyURL's no-auth API. Returns the original URL on failure."""
    if not long_url:
        return long_url
    try:
        resp = requests.get(
            "https://tinyurl.com/api-create.php",
            params={"url": long_url},
            timeout=5,
        )
        if resp.status_code == 200 and resp.text.startswith("http"):
            return resp.text.strip()
        logger.warning("TinyURL returned %s: %s", resp.status_code, resp.text[:100])
    except Exception as e:
        logger.warning("TinyURL request failed: %s", e)
    return long_url
