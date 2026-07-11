"""briefing pack — the full daily briefing."""

from services.skills.registry import Skill, register

SKILL = register(Skill(
    id="briefing",
    title="Briefing",
    order=40,
    actions=("show_briefing",),
    flag="briefing",
    prompt='- "show_briefing" — full daily briefing (params: {})',
))
