"""core pack — plain conversation. Always on; can't be disabled."""

from services.skills.registry import Skill, register

SKILL = register(Skill(
    id="core",
    title="Conversation",
    order=0,
    actions=("chat",),
    flag="core",
    always_on=True,
    prompt='- "chat" — just reply conversationally (params: {})',
))
