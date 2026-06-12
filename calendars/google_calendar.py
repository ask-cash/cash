"""
google_calendar.py — Google Calendar integration.
Handles fetching events, detecting conflicts, and creating/moving events.
"""

import logging
import os
import datetime as dt
from typing import Optional
from services.user_profile import today as ist_today

logger = logging.getLogger(__name__)

from googleapiclient.discovery import build

from services.google_auth import load_credentials

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive.file",  # upload + attach files the app creates
]

GOOGLE_TOKEN_SECRET = "google_token"


def get_calendar_service(
    creds_path: str = "credentials.json",
    token_path: str = "token.json",
):
    """Build an authorized Google Calendar API service for the active tenant.

    Credentials come from the per-tenant secret vault (file fallback locally).
    Raises RuntimeError if the tenant hasn't connected Google yet — connecting
    is handled by the gateway OAuth flow / scripts/auth_google.py.
    """
    creds = load_credentials(GOOGLE_TOKEN_SECRET, SCOPES, token_path)
    if creds is None or not creds.valid:
        raise RuntimeError("Google Calendar not connected — run /connect_google")
    logger.debug("Google Calendar service built successfully")
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
        return self.get_events_for_date(ist_today(), timezone)

    def get_events_for_date(self, date: dt.date, timezone: str = "Asia/Kolkata") -> list[dict]:
        """Get events for a specific date across all calendars."""
        logger.info("Fetching Google Calendar events for date=%s", date)
        start = dt.datetime.combine(date, dt.time.min).isoformat() + "Z"
        end = dt.datetime.combine(date, dt.time.max).isoformat() + "Z"

        calendar_list = self.service.calendarList().list().execute()
        all_events = []

        for cal in calendar_list.get("items", []):
            cal_id = cal["id"]
            cal_name = cal.get("summary", cal_id)
            logger.debug("Fetching events from calendar '%s' (%s)", cal_name, cal_id)
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
            items = events_result.get("items", [])
            logger.debug("Found %d event(s) in calendar '%s'", len(items), cal_name)
            for ev in items:
                ev["_calendar_name"] = cal_name
                ev["_calendar_id"] = cal_id
                all_events.append(ev)

        def sort_key(e):
            s = e.get("start", {})
            return s.get("dateTime", s.get("date", ""))

        all_events.sort(key=sort_key)
        logger.info("Total Google Calendar events fetched for %s: %d", date, len(all_events))
        return all_events

    def get_upcoming_events(self, hours: int = 2, timezone: str = "Asia/Kolkata") -> list[dict]:
        """Get events in the next N hours."""
        logger.info("Fetching upcoming Google Calendar events for the next %d hour(s)", hours)
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
        items = events_result.get("items", [])
        logger.info("Found %d upcoming event(s) in the next %d hour(s)", len(items), hours)
        return items

    # ------------------------------------------------------------------
    # Conflict Detection
    # ------------------------------------------------------------------
    def find_conflicts(self, events: list[dict]) -> list[tuple[dict, dict]]:
        """Find overlapping event pairs."""
        logger.debug("Checking for conflicts among %d event(s)", len(events))
        conflicts = []
        for i in range(len(events)):
            for j in range(i + 1, len(events)):
                a_end = self._parse_event_time(events[i], "end")
                b_start = self._parse_event_time(events[j], "start")
                a_start = self._parse_event_time(events[i], "start")
                b_end = self._parse_event_time(events[j], "end")
                if a_end and b_start and a_start and b_end:
                    if a_start < b_end and b_start < a_end:
                        logger.warning(
                            "Conflict detected: '%s' overlaps with '%s'",
                            events[i].get("summary", "?"),
                            events[j].get("summary", "?"),
                        )
                        conflicts.append((events[i], events[j]))
        logger.info("Conflict check complete: %d conflict(s) found", len(conflicts))
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
        attachments: Optional[list[dict]] = None,
    ) -> dict:
        """Create a new calendar event.

        `attachments` should be a list of dicts shaped like Google Calendar's
        attachment schema: {"fileUrl": "...", "title": "...", "mimeType": "..."}.
        """
        logger.info("Creating Google Calendar event '%s' from %s to %s on calendar '%s'",
                    title, start, end, calendar_id)
        event = {
            "summary": title,
            "start": {"dateTime": start.isoformat(), "timeZone": "Asia/Kolkata"},
            "end": {"dateTime": end.isoformat(), "timeZone": "Asia/Kolkata"},
            "description": description,
        }
        if attachments:
            event["attachments"] = attachments
        result = (
            self.service.events()
            .insert(
                calendarId=calendar_id,
                body=event,
                supportsAttachments=bool(attachments),
            )
            .execute()
        )
        logger.info("Event created with id='%s'", result.get("id"))
        return result

    def move_event(self, event_id: str, new_start: dt.datetime, duration_minutes: int,
                   calendar_id: str = "primary") -> dict:
        """Move an event to a new time, keeping its duration."""
        logger.info("Moving Google Calendar event id='%s' to %s (duration=%d min) on calendar '%s'",
                    event_id, new_start, duration_minutes, calendar_id)
        new_end = new_start + dt.timedelta(minutes=duration_minutes)
        body = {
            "start": {"dateTime": new_start.isoformat(), "timeZone": "Asia/Kolkata"},
            "end": {"dateTime": new_end.isoformat(), "timeZone": "Asia/Kolkata"},
        }
        result = (
            self.service.events()
            .patch(calendarId=calendar_id, eventId=event_id, body=body)
            .execute()
        )
        logger.info("Event id='%s' moved successfully", event_id)
        return result

    def delete_event(self, event_id: str, calendar_id: str = "primary"):
        """Delete a calendar event."""
        logger.info("Deleting Google Calendar event id='%s' from calendar '%s'", event_id, calendar_id)
        self.service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        logger.info("Event id='%s' deleted successfully", event_id)


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
