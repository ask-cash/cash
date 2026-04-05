"""
outlook_calendar.py — Microsoft Outlook / Office 365 Calendar integration.
Uses MSAL (Microsoft Authentication Library) + Microsoft Graph API.
"""

import os
import json
import datetime as dt
from typing import Optional

import msal
import requests
from dotenv import load_dotenv

load_dotenv()

GRAPH_URL = "https://graph.microsoft.com/v1.0"
SCOPES = ["Calendars.ReadWrite", "User.Read"]


class OutlookCalendarManager:
    def __init__(self):
        self.client_id = os.getenv("OUTLOOK_CLIENT_ID", "")
        self.client_secret = os.getenv("OUTLOOK_CLIENT_SECRET", "")
        self.tenant_id = os.getenv("OUTLOOK_TENANT_ID", "common")
        self.token_path = os.getenv("OUTLOOK_TOKEN_PATH", "outlook_token.json")
        self.enabled = bool(self.client_id and self.client_secret)
        self._token_cache = msal.SerializableTokenCache() if self.enabled else None
        self._app = None

        if self.enabled:
            self._load_cache()
            self._app = msal.ConfidentialClientApplication(
                self.client_id,
                authority=f"https://login.microsoftonline.com/{self.tenant_id}",
                client_credential=self.client_secret,
                token_cache=self._token_cache,
            )

    def _load_cache(self):
        if os.path.exists(self.token_path):
            with open(self.token_path, "r") as f:
                self._token_cache.deserialize(f.read())

    def _save_cache(self):
        if self._token_cache and self._token_cache.has_state_changed:
            with open(self.token_path, "w") as f:
                f.write(self._token_cache.serialize())

    def get_access_token(self) -> Optional[str]:
        """Get a valid access token (from cache or refresh)."""
        if not self.enabled:
            return None

        accounts = self._app.get_accounts()
        result = None
        if accounts:
            result = self._app.acquire_token_silent(SCOPES, account=accounts[0])

        if not result:
            flow = self._app.initiate_device_flow(scopes=SCOPES)
            if "user_code" in flow:
                print(f"\n🔐 Outlook Auth: Go to {flow['verification_uri']}")
                print(f"   Enter code: {flow['user_code']}\n")
                result = self._app.acquire_token_by_device_flow(flow)

        if result and "access_token" in result:
            self._save_cache()
            return result["access_token"]
        return None

    def _headers(self) -> dict:
        token = self.get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Fetch Events
    # ------------------------------------------------------------------
    def get_events_for_date(self, date: dt.date, timezone: str = "Asia/Kolkata") -> list[dict]:
        """Get all Outlook calendar events for a specific date."""
        if not self.enabled:
            return []

        start = dt.datetime.combine(date, dt.time.min).isoformat()
        end = dt.datetime.combine(date, dt.time.max).isoformat()

        url = (
            f"{GRAPH_URL}/me/calendarview"
            f"?startdatetime={start}&enddatetime={end}"
            f"&$orderby=start/dateTime"
            f"&$top=50"
        )
        headers = self._headers()
        headers["Prefer"] = f'outlook.timezone="{timezone}"'

        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            return []

        events = resp.json().get("value", [])
        normalized = []
        for ev in events:
            normalized.append({
                "id": ev.get("id"),
                "summary": ev.get("subject", "(No title)"),
                "start": {"dateTime": ev.get("start", {}).get("dateTime", "")},
                "end": {"dateTime": ev.get("end", {}).get("dateTime", "")},
                "description": ev.get("bodyPreview", ""),
                "location": ev.get("location", {}).get("displayName", ""),
                "_calendar_name": "Outlook",
                "_calendar_id": "outlook",
                "_source": "outlook",
                "attendees": [
                    {
                        "email": a.get("emailAddress", {}).get("address", ""),
                        "responseStatus": a.get("status", {}).get("response", "none"),
                        "self": a.get("status", {}).get("response", "") != "",
                    }
                    for a in ev.get("attendees", [])
                ],
            })
        return normalized

    def get_today_events(self, timezone: str = "Asia/Kolkata") -> list[dict]:
        return self.get_events_for_date(dt.date.today(), timezone)

    # ------------------------------------------------------------------
    # Create / Update
    # ------------------------------------------------------------------
    def create_event(
        self,
        title: str,
        start: dt.datetime,
        end: dt.datetime,
        description: str = "",
        timezone: str = "Asia/Kolkata",
    ) -> Optional[dict]:
        if not self.enabled:
            return None

        body = {
            "subject": title,
            "start": {"dateTime": start.isoformat(), "timeZone": timezone},
            "end": {"dateTime": end.isoformat(), "timeZone": timezone},
            "body": {"contentType": "text", "content": description},
        }
        resp = requests.post(f"{GRAPH_URL}/me/events", headers=self._headers(), json=body)
        return resp.json() if resp.status_code in (200, 201) else None

    def move_event(
        self,
        event_id: str,
        new_start: dt.datetime,
        duration_minutes: int,
        timezone: str = "Asia/Kolkata",
    ) -> Optional[dict]:
        if not self.enabled:
            return None

        new_end = new_start + dt.timedelta(minutes=duration_minutes)
        body = {
            "start": {"dateTime": new_start.isoformat(), "timeZone": timezone},
            "end": {"dateTime": new_end.isoformat(), "timeZone": timezone},
        }
        resp = requests.patch(
            f"{GRAPH_URL}/me/events/{event_id}",
            headers=self._headers(),
            json=body,
        )
        return resp.json() if resp.status_code == 200 else None

    def format_event(self, event: dict) -> str:
        title = event.get("summary", "(No title)")
        start = event.get("start", {}).get("dateTime", "?")
        if "T" in start:
            start = start.split("T")[1][:5]
        return f"• {start} — {title}  [Outlook]"
