"""
gmail.py — Gmail API integration for fetching, searching, and managing emails.
Reuses Google OAuth credentials with Gmail-specific scopes.
"""

import os
import base64
import datetime as dt
import logging
from typing import Optional
from email.utils import parseaddr

from googleapiclient.discovery import build

from services.google_auth import load_credentials

logger = logging.getLogger(__name__)

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

GMAIL_TOKEN_PATH = os.getenv("GMAIL_TOKEN_PATH", "gmail_token.json")
GMAIL_TOKEN_SECRET = "gmail_token"


def get_gmail_service(
    creds_path: str = "credentials.json",
    token_path: str = None,
):
    """Build an authorized Gmail API service for the active tenant.

    Credentials come from the per-tenant secret vault (file fallback locally).
    Raises RuntimeError if the tenant hasn't connected Gmail yet.
    """
    token_path = token_path or GMAIL_TOKEN_PATH
    creds = load_credentials(GMAIL_TOKEN_SECRET, GMAIL_SCOPES, token_path)
    if creds is None or not creds.valid:
        raise RuntimeError("Gmail not connected — run /connect_gmail")
    return build("gmail", "v1", credentials=creds)


class GmailManager:
    def __init__(self):
        creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
        self.service = get_gmail_service(creds_path)

    def fetch_recent_emails(self, max_results: int = 20, query: str = "is:inbox") -> list[dict]:
        """Fetch recent emails from inbox."""
        results = (
            self.service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
        messages = results.get("messages", [])
        emails = []
        for msg_ref in messages:
            email = self._get_email_details(msg_ref["id"])
            if email:
                emails.append(email)
        return emails

    def fetch_unread_emails(self, max_results: int = 20) -> list[dict]:
        """Fetch unread emails from inbox."""
        return self.fetch_recent_emails(max_results=max_results, query="is:inbox is:unread")

    def _get_email_details(self, msg_id: str) -> Optional[dict]:
        """Get full details of a single email."""
        try:
            msg = (
                self.service.users()
                .messages()
                .get(userId="me", id=msg_id, format="metadata",
                     metadataHeaders=["From", "To", "Subject", "Date"])
                .execute()
            )
            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            sender_name, sender_email = parseaddr(headers.get("From", ""))

            return {
                "id": msg_id,
                "thread_id": msg.get("threadId", ""),
                "subject": headers.get("Subject", "(No subject)"),
                "from_name": sender_name or sender_email,
                "from_email": sender_email,
                "to": headers.get("To", ""),
                "date": headers.get("Date", ""),
                "snippet": msg.get("snippet", ""),
                "label_ids": msg.get("labelIds", []),
                "is_unread": "UNREAD" in msg.get("labelIds", []),
            }
        except Exception as e:
            logger.error(f"Error fetching email {msg_id}: {e}")
            return None

    def get_email_body(self, msg_id: str) -> str:
        """Get the plain text body of an email (first 500 chars for classification)."""
        try:
            msg = (
                self.service.users()
                .messages()
                .get(userId="me", id=msg_id, format="full")
                .execute()
            )
            return self._extract_body(msg.get("payload", {}))[:500]
        except Exception as e:
            logger.error(f"Error fetching email body {msg_id}: {e}")
            return ""

    def _extract_body(self, payload: dict) -> str:
        """Recursively extract plain text from email payload."""
        if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

        for part in payload.get("parts", []):
            text = self._extract_body(part)
            if text:
                return text
        return ""

    def mark_as_read(self, msg_id: str):
        """Mark an email as read."""
        self.service.users().messages().modify(
            userId="me", id=msg_id,
            body={"removeLabelIds": ["UNREAD"]}
        ).execute()

    def get_email_count(self) -> dict:
        """Get counts of unread and total inbox emails."""
        profile = self.service.users().getProfile(userId="me").execute()
        unread_result = (
            self.service.users()
            .messages()
            .list(userId="me", q="is:inbox is:unread", maxResults=1)
            .execute()
        )
        return {
            "total_messages": profile.get("messagesTotal", 0),
            "unread": unread_result.get("resultSizeEstimate", 0),
        }
