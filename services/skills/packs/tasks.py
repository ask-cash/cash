"""tasks pack — the daily task list."""

from services.skills.registry import Skill, register

SKILL = register(Skill(
    id="tasks",
    title="Tasks",
    order=10,
    actions=("add_task", "mark_done", "show_tasks"),
    flag="tasks",
    prompt='''- "add_task" — add a task (params: {"task": "...", "time": "HH:MM", "category": "..."})
- "mark_done" — mark task done (params: {"task_text": "..."})
- "show_tasks" — show task list (params: {})''',
))
