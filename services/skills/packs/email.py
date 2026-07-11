"""email pack — checking and classifying recent email."""

from services.skills.registry import Skill, register

SKILL = register(Skill(
    id="email",
    title="Email",
    order=100,
    actions=("check_emails", "show_email_prefs"),
    flag="email",
    prompt='''- "check_emails" — check and classify recent emails (params: {})
- "show_email_prefs" — show learned email filtering preferences (params: {})''',
))
