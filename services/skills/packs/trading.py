"""trading pack — the user's trading rules."""

from services.skills.registry import Skill, register

SKILL = register(Skill(
    id="trading",
    title="Trading",
    order=30,
    actions=("show_trading_rules", "add_trading_rule"),
    flag="trading",
    prompt='''- "show_trading_rules" — display trading rules (params: {})
- "add_trading_rule" — add a rule (params: {"rule": "..."})''',
))
