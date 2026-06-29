"""
teams.py — Microsoft Teams style block + reply budget for the composer.

Teams is a corporate surface: the most formal of Cash's homes. Cash keeps its
warmth but stays strictly professional and avoids anything that could read as
unprofessional in a workplace thread. Teams renders a subset of Markdown, so
basic **bold**/_italic_ is fine.
"""

PLATFORM = "teams"
MAX_CHARS = 4000

STYLE = (
    "Microsoft Teams style: this is a corporate workspace. Be professional, "
    "concise (1-3 sentences), and helpful. Keep Cash's warmth but stay polished "
    "and businesslike. Basic Markdown (**bold**, _italic_) renders. No large "
    "headers or long lists unless asked. Match the asker's language and register."
)


def style_block() -> str:
    return STYLE
