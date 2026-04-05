"""
auth_google.py — One-time script to authorize Google Calendar access.
Run this locally before deploying. It opens a browser for OAuth consent.

Usage:
    python scripts/auth_google.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calendars.google_calendar import get_calendar_service

if __name__ == "__main__":
    print("🔐 Authorizing Google Calendar access...")
    print("A browser window will open. Sign in and grant access.\n")
    service = get_calendar_service()
    calendars = service.calendarList().list().execute()
    print("✅ Success! Connected calendars:")
    for cal in calendars.get("items", []):
        print(f"   • {cal['summary']} ({cal['id']})")
    print("\ntoken.json has been saved. You can now run the bot.")
