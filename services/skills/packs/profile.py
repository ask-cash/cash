"""profile pack — saving what the user tells us about themselves."""

from services.skills.registry import Skill, register

SKILL = register(Skill(
    id="profile",
    title="Profile",
    order=60,
    actions=("update_profile",),
    flag="profile",
    prompt='''- "update_profile" — save what the user tells you about themselves / their routine (name, timezone, wake/sleep, work-study-gym-market hours, recurring commitments, how they want help). Use whenever they share any of this — especially during cold-start setup. params: a PARTIAL profile with ONLY the fields they gave, e.g. {"name": "...", "timezone": "Area/City", "wake_time": "HH:MM", "sleep_time": "HH:MM", "gym": {"default_time": "HH:MM", "duration_minutes": N, "days": ["Mon","Wed","Fri"]}, "trading": {"market_open": "HH:MM", "market_close": "HH:MM"}, "default_tasks": [{"time": "HH:MM", "category": "...", "task": "..."}]}''',
))
