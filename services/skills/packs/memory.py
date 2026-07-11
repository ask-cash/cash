"""memory pack — searching past conversations and reviewing decisions."""

from services.skills.registry import Skill, register

SKILL = register(Skill(
    id="memory",
    title="Memory",
    order=80,
    actions=("search_memory", "show_decisions"),
    flag="memory",
    prompt='''- "search_memory" — search past conversations (params: {"query": "..."})
- "show_decisions" — show active decisions/intentions (params: {})''',
))
