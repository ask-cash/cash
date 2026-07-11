"""reminders pack — one-off proactive pings."""

from services.skills.registry import Skill, register

SKILL = register(Skill(
    id="reminders",
    title="Reminders",
    order=50,
    actions=("set_reminder", "set_reminders", "show_reminders"),
    flag="reminders",
    prompt='''- "set_reminder" — schedule ONE proactive ping at a specific FUTURE time. params: {"text": "what to remind them about", "date": "YYYY-MM-DD", "time": "HH:MM" (24h)}
  Resolve relative times to a concrete date + 24h time using CURRENT TIME — "in 30 minutes", "at 5pm", "tonight", "tomorrow 9am" all become a concrete date+time. YES you CAN send proactive reminders now — NEVER say you can only respond when messaged.
  TIME-RELATIVE TO AN EVENT: for "an hour before my dentist appointment" / "30 min before standup", find that event in the CALENDAR block above and subtract from its REAL start time (dentist at 18:00 → remind at 17:00). NEVER guess the event's time — if it's not in the CALENDAR block, say you can't find that event and ask for the time.
- "set_reminders" — schedule MULTIPLE reminders in one go. Use this whenever the user asks for more than one reminder in a single message (a single set_reminder can only create one). params: {"reminders": [{"text": "...", "date": "YYYY-MM-DD", "time": "HH:MM"}, {"text": "...", "date": "...", "time": "..."}]}
- "show_reminders" — list the user's pending reminders (params: {})''',
))
