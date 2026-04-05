"""
auth_outlook.py — One-time script to authorize Outlook Calendar access.
Uses device code flow — works even on headless servers.

Usage:
    python scripts/auth_outlook.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    client_id = os.getenv("OUTLOOK_CLIENT_ID")
    if not client_id:
        print("❌ OUTLOOK_CLIENT_ID not set in .env — skipping Outlook setup.")
        print("   Set it up at https://portal.azure.com → App registrations")
        sys.exit(0)

    from calendars.outlook_calendar import OutlookCalendarManager

    print("🔐 Authorizing Outlook Calendar access...")
    print("   Follow the instructions below:\n")

    outlook = OutlookCalendarManager()
    token = outlook.get_access_token()

    if token:
        print("\n✅ Outlook Calendar connected!")
        events = outlook.get_today_events()
        print(f"   Found {len(events)} events today.")
    else:
        print("\n❌ Failed to connect. Check your credentials.")
