"""calendars_status pack — showing which calendars are connected."""

from services.skills.registry import Skill, register

SKILL = register(Skill(
    id="calendars_status",
    title="Calendar status",
    order=90,
    actions=("show_calendars",),
    flag="calendars_status",
    prompt='- "show_calendars" — show connected calendar status (params: {})',
))
