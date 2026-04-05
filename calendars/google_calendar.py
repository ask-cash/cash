"""
google_calendar.py — Google Calendar integration.
Handles fetching events, detecting conflicts, and creating/moving events.
"""

import os
import datetime as dt
from typing import Optional

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def get_calendar_service(
    creds_path: str = "credentials.json",
    token_path: str = "token.json",
):
    """Build and return an authorized Google Calendar API service."""
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return build("calendar", "v3", credentials=creds)


class GoogleCalendarManager:
    def __init__(self):
        creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
        token_path = os.getenv("GOOGLE_TOKEN_PATH", "token.json")
        self.service = get_calendar_service(creds_path, token_path)

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------
    def get_today_events(self, timezone: str = "Asia/Kolkata") -> list[dict]:
        """Get all events for today."""
        return self.get_events_for_date(dt.date.today(), timezone)

    def get_events_for_date(self, date: dt.date, timezone: str = "Asia/Kolkata") -> list[dict]:
        """Get events for a specific date across all calendars."""
        start = dt.datetime.combine(date, dt.time.min).isoformat() + "Z"
        end = dt.datetime.combine(date, dt.time.max).isoformat() + "Z"

        calendar_list = self.service.calendarList().list().execute()
        all_events = []

        for cal in calendar_list.get("items", []):
            cal_id = cal["id"]
            cal_name = cal.get("summary", cal_id)
            events_result = (
                self.service.events()
                .list(
                    calendarId=cal_id,
                    timeMin=start,
                    timeMax=end,
                    singleEvents=True,
                    orderBy="startTime",
                    timeZone=timezone,
                )
                .execute()
            )
            for ev in events_result.get("items", []):
                ev["_calendar_name"] = cal_name
                ev["_calendar_id"] = cal_id
                all_events.append(ev)

        def sort_key(e):
            s = e.get("start", {})
            return s.get("dateTime", s.get("date", ""))

        all_events.sort(key=sort_key)
        return all_events

    def get_upcoming_events(self, hours: int = 2, timezone: str = "Asia/Kolkata") -> list[dict]:
        """Get events in the next N hours."""
        now = dt.datetime.utcnow()
        end = now + dt.timedelta(hours=hours)
        events_result = (
            self.service.events()
            .list(
                calendarId="primary",
                timeMin=now.isoformat() + "Z",
                timeMax=end.isoformat() + "Z",
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        return events_result.get("items", [])

    # ------------------------------------------------------------------
    # Conflict Detection
    # ------------------------------------------------------------------
    def find_conflicts(self, events: list[dict]) -> list[tuple[dict, dict]]:
        """Find overlapping event pairs."""
        conflicts = []
        for i in range(len(events)):
            for j in range(i + 1, len(events)):
                a_end = self._parse_event_time(events[i], "end")
                b_start = self._parse_event_time(events[j], "start")
                a_start = self._parse_event_time(events[i], "start")
                b_end = self._parse_event_time(events[j], "end")
                if a_end and b_start and a_start and b_end:
                    if a_start < b_end and b_start < a_end:
                        conflicts.append((events[i], events[j]))
        return conflicts

    # ------------------------------------------------------------------
    # Create / Update
    # ------------------------------------------------------------------
    def create_event(
        self,
        title: str,
        start: dt.datetime,
        end: dt.datetime,
        calendar_id: str = "primary",
        description: str = "",
    ) -> dict:
        """Create a new calendar event."""
        event = {
            "summary": title,
            "start": {"dateTime": start.isoformat(), "timeZone": "Asia/Kolkata"},
            "end": {"dateTime": end.isoformat(), "timeZone": "Asia/Kolkata"},
            "description": description,
        }
        return self.service.events().insert(calendarId=calendar_id, body=event).execute()

    def move_event(self, event_id: str, new_start: dt.datetime, duration_minutes: int,
                   calendar_id: str = "primary") -> dict:
        """Move an event to a new time, keeping its duration."""
        new_end = new_start + dt.timedelta(minutes=duration_minutes)
        body = {
            "start": {"dateTime": new_start.isoformat(), "timeZone": "Asia/Kolkata"},
            "end": {"dateTime": new_end.isoformat(), "timeZone": "Asia/Kolkata"},
        }
        return (
            self.service.events()
            .patch(calendarId=calendar_id, eventId=event_id, body=body)
            .execute()
        )

    def delete_event(self, event_id: str, calendar_id: str = "primary"):
        """Delete a calendar event."""
        self.service.events().delete(calendarId=calendar_id, eventId=event_id).execute()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _parse_event_time(self, event: dict, key: str) -> Optional[dt.datetime]:
        raw = event.get(key, {}).get("dateTime")
        if raw:
            return dt.datetime.fromisoformat(raw)
        return None

    def format_event(self, event: dict) -> str:
        """Human-readable single-line summary."""
        title = event.get("summary", "(No title)")
        start = event.get("start", {}).get("dateTime", event.get("start", {}).get("date", "?"))
        cal = event.get("_calendar_name", "")
        if "T" in start:
            start = start.split("T")[1][:5]
        return f"• {start} — {title}  [{cal}]" if cal else f"• {start} — {title}"

    def format_events(self, events: list[dict]) -> str:
        if not events:
            return "No events found."
        return "\n".join(self.format_event(e) for e in events)
