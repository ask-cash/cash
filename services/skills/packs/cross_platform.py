"""cross_platform pack — proactively reaching the user on another platform."""

from services.skills.registry import Skill, register

SKILL = register(Skill(
    id="cross_platform",
    title="Cross-platform messaging",
    order=70,
    actions=("send_platform_message",),
    flag="cross_platform",
    prompt='''- "send_platform_message" — proactively send a message to the user on ANOTHER platform (right now: Discord). Use whenever the user asks you to message / ping / DM / "tell me on" Discord. params: {"platform": "discord", "text": "the message to send"}. It delivers to the user's own Discord DM, but ONLY if they've connected their Discord. The action checks this and replies honestly — so do NOT promise delivery yourself; just route the request and let the action's result speak.''',
))
