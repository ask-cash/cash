"""
unified.py — Merges events from Google Calendar + Outlook into one view.
"""

import datetime as dt
from typing import Optional

from calendars.google_calendar import GoogleCalendarManager
from calendars.outlook_calendar import OutlookCalendarManager


class UnifiedCalendar:
    """Single interface to query both Google Calendar and Outlook."""

    def __init__(self):
        self.google: Optional[GoogleCalendarManager] = None
        self.outlook: Optional[OutlookCalendarManager] = None

        try:
            self.google = GoogleCalendarManager()
        except Exception as e:
            print(f"⚠️ Google Calendar not available: {e}")

        try:
            self.outlook = OutlookCalendarManager()
            if not self.outlook.enabled:
                self.outlook = None
        except Exception as e:
            print(f"⚠️ Outlook Calendar not available: {e}")

    def get_today_events(self, timezone: str = "Asia/Kolkata") -> list[dict]:
        return self.get_events_for_date(dt.date.today(), timezone)

    def get_events_for_date(self, date: dt.date, timezone: str = "Asia/Kolkata") -> list[dict]:
        """Fetch and merge events from all connected calendars."""
        all_events = []

        if self.google:
            try:
                google_events = self.google.get_events_for_date(date, timezone)
                for ev in google_events:
                    ev.setdefault("_source", "google")
                all_events.extend(google_events)
            except Exception as e:
                print(f"Google Calendar fetch error: {e}")

        if self.outlook:
            try:
                outlook_events = self.outlook.get_events_for_date(date, timezone)
                all_events.extend(outlook_events)
            except Exception as e:
                print(f"Outlook Calendar fetch error: {e}")

        def sort_key(e):
            s = e.get("start", {})
            return s.get("dateTime", s.get("date", ""))
        all_events.sort(key=sort_key)

        return all_events

    def get_tomorrow_events(self, timezone: str = "Asia/Kolkata") -> list[dict]:
        return self.get_events_for_date(dt.date.today() + dt.timedelta(days=1), timezone)

    def create_event(self, title: str, start: dt.datetime, end: dt.datetime,
                     calendar: str = "google", description: str = "") -> Optional[dict]:
        """Create event on specified calendar ('google' or 'outlook')."""
        if calendar == "outlook" and self.outlook:
            return self.outlook.create_event(title, start, end, description)
        elif self.google:
            return self.google.create_event(title, start, end, description=description)
        return None

    def move_event(self, event_id: str, new_start: dt.datetime, duration_minutes: int,
                   source: str = "google") -> Optional[dict]:
        if source == "outlook" and self.outlook:
            return self.outlook.move_event(event_id, new_start, duration_minutes)
        elif self.google:
            return self.google.move_event(event_id, new_start, duration_minutes)
        return None

    def find_conflicts(self, events: list[dict]) -> list[tuple[dict, dict]]:
        """Find overlapping event pairs across all calendars."""
        conflicts = []
        for i in range(len(events)):
            for j in range(i + 1, len(events)):
                a_start = self._parse_time(events[i], "start")
                a_end = self._parse_time(events[i], "end")
                b_start = self._parse_time(events[j], "start")
                b_end = self._parse_time(events[j], "end")
                if a_start and a_end and b_start and b_end:
                    if a_start < b_end and b_start < a_end:
                        conflicts.append((events[i], events[j]))
        return conflicts

    def format_events(self, events: list[dict]) -> str:
        if not events:
            return "No events found."
        lines = []
        for ev in events:
            title = ev.get("summary", "(No title)")
            start = ev.get("start", {}).get("dateTime", ev.get("start", {}).get("date", "?"))
            source = ev.get("_source", "")
            cal_name = ev.get("_calendar_name", source)
            if "T" in start:
                start = start.split("T")[1][:5]
            tag = f"  [{cal_name}]" if cal_name else ""
            lines.append(f"• {start} — {title}{tag}")
        return "\n".join(lines)

    def _parse_time(self, event: dict, key: str) -> Optional[dt.datetime]:
        raw = event.get(key, {}).get("dateTime")
        if raw:
            try:
                return dt.datetime.fromisoformat(raw)
            except ValueError:
                return None
        return None

    def sources_summary(self) -> str:
        """Return which calendars are connected."""
        sources = []
        if self.google:
            sources.append("✅ Google Calendar")
        else:
            sources.append("❌ Google Calendar (not connected)")
        if self.outlook:
            sources.append("✅ Outlook Calendar")
        else:
            sources.append("❌ Outlook Calendar (not configured)")
        return "\n".join(sources)
