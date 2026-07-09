"""
heartbeat.py — Cash's hourly pulse.

Unlike a schedule (which has a fixed agenda), the heartbeat has none: every hour
Cash re-reads her NOW scratchpad, her open loops, and the day's unfinished tasks,
and decides *for herself* whether anything is worth a nudge. It's how she stays
present when no one's asking.

Design rules (from the docs):
  * **Never runs at process startup or on an unconditional timer** — it is
    invoked only by the scheduled hourly job, so it costs the guardian nothing
    until Cash is actually watching over a real day.
  * **Guardian-disableable** — a per-tenant toggle silences it.
  * **Delivery-decoupled** — ``run_heartbeat`` only *decides* and *composes*; it
    returns ``{"speak": bool, "message": str}`` and the job layer delivers. This
    keeps it fully testable (injectable ``llm=``) and lets Feature 5's
    notification router own routing later.
"""

from __future__ import annotations

import json
import logging
import os
import re

from services import memory, persona, state_store, task_tracker

logger = logging.getLogger(__name__)

NAMESPACE = "heartbeat"
_SETTINGS_KEY = "settings"

_SYSTEM_TAIL = """
You are doing a quiet hourly check-in on your guardian — nobody asked you to. Below is
what you're currently tracking. Decide whether anything genuinely warrants pinging them
RIGHT NOW, or whether it's better to stay quiet and not be annoying.

Speak up only if something is due, slipping, or worth a nudge. A calm day = silence.

Respond with ONLY this JSON (no markdown, no backticks):
{"speak": true|false, "message": "<a short in-character nudge, or empty if not speaking>"}
"""


def is_enabled() -> bool:
    doc = state_store.read_json(NAMESPACE, _SETTINGS_KEY, default={"enabled": True})
    return bool(doc.get("enabled", True)) if isinstance(doc, dict) else True


def set_enabled(on: bool) -> None:
    state_store.write_json(NAMESPACE, _SETTINGS_KEY, {"enabled": bool(on)})


def gather_context() -> dict:
    """What might need attention right now. Pure reads — no LLM, no delivery."""
    open_loops = [d for d in memory.get_active_decisions() if not d.get("fulfilled")]
    summary = task_tracker.get_tasks_summary()
    return {
        "open_loops": open_loops,
        "pending_tasks": summary["pending"],
        "now": persona.now_text().strip(),
    }


def _has_anything(ctx: dict) -> bool:
    return bool(ctx["open_loops"] or ctx["pending_tasks"] or ctx["now"])


def _render_context(ctx: dict) -> str:
    lines = []
    if ctx["now"]:
        lines.append(f"NOW (your current focus):\n{ctx['now']}")
    if ctx["open_loops"]:
        lines.append("OPEN LOOPS:")
        for d in ctx["open_loops"][-8:]:
            age = memory._age_days(d.get("made_date"))
            lines.append(f"  • {d['decision']} ({d.get('scope', 'today')}, day {age + 1})")
    if ctx["pending_tasks"]:
        lines.append("UNFINISHED TASKS TODAY:")
        for t in ctx["pending_tasks"][:10]:
            lines.append(f"  • {t['task']}")
    return "\n".join(lines)


def _default_llm(system: str, user: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return resp.content[0].text


def _parse_decision(raw: str) -> dict:
    text = (raw or "").replace("```json", "").replace("```", "").strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {"speak": False, "message": ""}
    try:
        d = json.loads(match.group(0), strict=False)
    except json.JSONDecodeError:
        return {"speak": False, "message": ""}
    return {"speak": bool(d.get("speak")), "message": (d.get("message") or "").strip()}


def run_heartbeat(llm=None) -> dict:
    """Decide whether Cash should nudge the guardian right now, and what to say.

    Returns ``{"spoke": bool, "message": str, "reason": str}``. Never delivers.
    ``llm`` is an injectable ``(system, user) -> str`` for testing.
    """
    if not is_enabled():
        return {"spoke": False, "message": "", "reason": "disabled"}

    ctx = gather_context()
    if not _has_anything(ctx):
        # Nothing to consider — don't even spend an LLM call.
        return {"spoke": False, "message": "", "reason": "nothing to check"}

    llm = llm or _default_llm
    system = persona.persona_system_block("owner") + "\n" + _SYSTEM_TAIL
    try:
        raw = llm(system, _render_context(ctx))
    except Exception:
        logger.exception("heartbeat: LLM call failed")
        return {"spoke": False, "message": "", "reason": "llm error"}

    decision = _parse_decision(raw)
    if decision["speak"] and decision["message"]:
        return {"spoke": True, "message": decision["message"], "reason": "nudge"}
    return {"spoke": False, "message": "", "reason": "stayed quiet"}
