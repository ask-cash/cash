"""
unified.py — Merges events from Google Calendar + Outlook into one view.
"""

import logging
import datetime as dt
from typing import Optional

logger = logging.getLogger(__name__)

from calendars.google_calendar import GoogleCalendarManager
from calendars.outlook_calendar import OutlookCalendarManager
from services.user_profile import today as ist_today


class UnifiedCalendar:
    """Single interface to query both Google Calendar and Outlook."""

    def __init__(self):
        self.google: Optional[GoogleCalendarManager] = None
        self.outlook: Optional[OutlookCalendarManager] = None

        try:
            self.google = GoogleCalendarManager()
            logger.info("Google Calendar initialized successfully")
        except Exception as e:
            logger.warning("Google Calendar not available: %s", e)
            print(f"⚠️ Google Calendar not available: {e}")

        try:
            self.outlook = OutlookCalendarManager()
            if not self.outlook.enabled:
                logger.info("Outlook Calendar not configured (missing credentials)")
                self.outlook = None
            else:
                logger.info("Outlook Calendar initialized successfully")
        except Exception as e:
            logger.warning("Outlook Calendar not available: %s", e)
            print(f"⚠️ Outlook Calendar not available: {e}")

    def get_today_events(self, timezone: str = "Asia/Kolkata") -> list[dict]:
        return self.get_events_for_date(ist_today(), timezone)

    def get_events_for_date(self, date: dt.date, timezone: str = "Asia/Kolkata") -> list[dict]:
        """Fetch and merge events from all connected calendars."""
        logger.info("Fetching unified calendar events for date=%s", date)
        all_events = []

        if self.google:
            try:
                google_events = self.google.get_events_for_date(date, timezone)
                for ev in google_events:
                    ev.setdefault("_source", "google")
                all_events.extend(google_events)
                logger.debug("Merged %d Google event(s)", len(google_events))
            except Exception as e:
                logger.error("Google Calendar fetch error: %s", e)
                print(f"Google Calendar fetch error: {e}")

        if self.outlook:
            try:
                outlook_events = self.outlook.get_events_for_date(date, timezone)
                all_events.extend(outlook_events)
                logger.debug("Merged %d Outlook event(s)", len(outlook_events))
            except Exception as e:
                logger.error("Outlook Calendar fetch error: %s", e)
                print(f"Outlook Calendar fetch error: {e}")

        def sort_key(e):
            s = e.get("start", {})
            return s.get("dateTime", s.get("date", ""))
        all_events.sort(key=sort_key)
        logger.info("Total unified events for %s: %d", date, len(all_events))
        return all_events

    def get_tomorrow_events(self, timezone: str = "Asia/Kolkata") -> list[dict]:
        return self.get_events_for_date(ist_today() + dt.timedelta(days=1), timezone)

    def create_event(self, title: str, start: dt.datetime, end: dt.datetime,
                     calendar: str = "google", description: str = "",
                     attachments: Optional[list[dict]] = None) -> Optional[dict]:
        """Create event on specified calendar ('google' or 'outlook').

        `attachments` is only honoured by the Google backend today.
        """
        logger.info("Creating event '%s' on %s calendar from %s to %s", title, calendar, start, end)
        if calendar == "outlook" and self.outlook:
            return self.outlook.create_event(title, start, end, description)
        elif self.google:
            return self.google.create_event(title, start, end, description=description,
                                            attachments=attachments)
        logger.warning("No calendar available to create event '%s'", title)
        return None

    def delete_event(self, event_id: str, source: str = "google") -> bool:
        """Delete an event from the specified calendar source."""
        logger.info("Deleting event id='%s' from %s calendar", event_id, source)
        if source == "outlook" and self.outlook:
            return self.outlook.delete_event(event_id)
        elif self.google:
            try:
                self.google.delete_event(event_id)
                return True
            except Exception as e:
                logger.error("Failed to delete Google event id='%s': %s", event_id, e)
                return False
        logger.warning("No calendar available to delete event id='%s'", event_id)
        return False

    def find_event(self, title: str = "", event_time: str = "",
                   date: dt.date = None) -> Optional[dict]:
        """Find an event by time and/or fuzzy title match.

        Matching strategy (in priority order):
        1. If event_time given, filter to events starting at that hour.
        2. Among time-matched events (or all events if no time), pick the
           best fuzzy title match.
        3. Fall back to substring match for simple cases.
        """
        if date is None:
            date = dt.date.today()
        logger.debug("Searching for event: title='%s', time='%s', date=%s",
                     title, event_time, date)
        events = self.get_events_for_date(date)
        if not events:
            logger.info("No events found on %s", date)
            return None

        # --- Step 1: filter by time if provided ---
        time_matched = events
        if event_time:
            time_matched = self._filter_by_time(events, event_time)
            logger.debug("Time filter '%s' matched %d event(s)", event_time, len(time_matched))
            # If exactly one event at that time and no title given, return it
            if len(time_matched) == 1 and not title:
                logger.info("Single event at %s: '%s'", event_time,
                           time_matched[0].get("summary"))
                return time_matched[0]

        # --- Step 2: fuzzy title match among candidates ---
        if title:
            pool = time_matched if time_matched else events
            best = self._best_title_match(pool, title)
            if best:
                logger.info("Best match for '%s': '%s' (score=%.2f)",
                           title, best[0].get("summary"), best[1])
                return best[0]

        # If we had time matches but no title match, return the first time match
        if event_time and time_matched:
            logger.info("Returning first time-matched event: '%s'",
                       time_matched[0].get("summary"))
            return time_matched[0]

        logger.info("No event found matching title='%s', time='%s' on %s",
                    title, event_time, date)
        return None

    # kept for backward compat — callers that only have a title
    def find_event_by_title(self, title: str, date: dt.date = None) -> Optional[dict]:
        return self.find_event(title=title, date=date)

    # ------------------------------------------------------------------
    # Private matching helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _filter_by_time(events: list[dict], time_str: str) -> list[dict]:
        """Filter events whose start hour matches the given time (HH:MM)."""
        try:
            target = dt.time.fromisoformat(time_str)
        except ValueError:
            return []
        matched = []
        for ev in events:
            raw = ev.get("start", {}).get("dateTime", "")
            if not raw:
                continue
            try:
                ev_start = dt.datetime.fromisoformat(raw)
                if ev_start.hour == target.hour and abs(ev_start.minute - target.minute) <= 5:
                    matched.append(ev)
            except ValueError:
                continue
        return matched

    @staticmethod
    def _title_similarity(a: str, b: str) -> float:
        """Word-overlap similarity between two strings (0.0 – 1.0).

        Handles extra/missing words, minor spelling differences, and
        common word swaps (e.g. "Review" vs "Look at").
        """
        if not a or not b:
            return 0.0
        words_a = set(a.lower().split())
        words_b = set(b.lower().split())
        # remove very short filler words for better matching
        stopwords = {"a", "an", "the", "at", "to", "of", "in", "on", "my", "is", "for"}
        words_a -= stopwords
        words_b -= stopwords
        if not words_a or not words_b:
            return 0.0
        intersection = words_a & words_b
        union = words_a | words_b
        return len(intersection) / len(union)

    @classmethod
    def _best_title_match(cls, events: list[dict], title: str,
                          threshold: float = 0.25) -> Optional[tuple[dict, float]]:
        """Return (event, score) for the best fuzzy title match above threshold."""
        best_event = None
        best_score = 0.0
        title_lower = title.lower()
        for ev in events:
            summary = ev.get("summary", "")
            # exact substring still wins immediately
            if title_lower in summary.lower():
                return (ev, 1.0)
            score = cls._title_similarity(title, summary)
            if score > best_score:
                best_score = score
                best_event = ev
        if best_event and best_score >= threshold:
            return (best_event, best_score)
        return None

    def move_event(self, event_id: str, new_start: dt.datetime, duration_minutes: int,
                   source: str = "google") -> Optional[dict]:
        logger.info("Moving event id='%s' to %s (duration=%d min) on %s calendar",
                    event_id, new_start, duration_minutes, source)
        if source == "outlook" and self.outlook:
            return self.outlook.move_event(event_id, new_start, duration_minutes)
        elif self.google:
            return self.google.move_event(event_id, new_start, duration_minutes)
        logger.warning("No calendar available to move event id='%s'", event_id)
        return None

    def find_conflicts(self, events: list[dict]) -> list[tuple[dict, dict]]:
        """Find overlapping event pairs across all calendars."""
        logger.debug("Checking for conflicts among %d event(s)", len(events))
        conflicts = []
        for i in range(len(events)):
            for j in range(i + 1, len(events)):
                a_start = self._parse_time(events[i], "start")
                a_end = self._parse_time(events[i], "end")
                b_start = self._parse_time(events[j], "start")
                b_end = self._parse_time(events[j], "end")
                if a_start and a_end and b_start and b_end:
                    if a_start < b_end and b_start < a_end:
                        logger.warning(
                            "Conflict detected: '%s' overlaps with '%s'",
                            events[i].get("summary", "?"),
                            events[j].get("summary", "?"),
                        )
                        conflicts.append((events[i], events[j]))
        logger.info("Conflict check complete: %d conflict(s) found", len(conflicts))
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
