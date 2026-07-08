"""
memory_reducer.py — off-hot-path memory consolidation.

The owner brain already extracts memory inline (its ``memory_ops``). The reducer
is the background sweep that catches what the hot path missed: it re-reads recent
conversation turns after the guardian goes idle and emits structured memory ops
(store_fact / store_decision / fulfill_decision), deduped by the same fingerprint
logic. It is side-effect-free until ``apply_ops`` runs the emitted ops through
``services.memory``.

Design rules (from the docs):
  * Never runs at process startup or on an unconditional timer — it is invoked
    from the worker after a conversation goes idle, so it costs the guardian
    nothing until they've actually talked.
  * The LLM call is injectable (``llm=`` callable) so the reducer is fully
    testable without a network or API key.
  * A per-tenant cursor tracks how far we've reduced, so each turn is considered
    at most once.
"""

from __future__ import annotations

import json
import logging
import os
import re

from services import memory, state_store

logger = logging.getLogger(__name__)

_CURSOR_KEY = "reducer_cursor"
_MAX_TURNS = 40  # bound the window we ask the model to consolidate

_SYSTEM = """You consolidate a user's recent messages into durable memory for their assistant.
Read the messages and output ONLY a JSON array of memory operations (no prose, no backticks).

Each op is one of:
  {"op": "store_fact", "fact": "<stable fact about the user>", "category": "preference|person|general|rule|feeling"}
  {"op": "store_decision", "decision": "<intention they stated>", "scope": "today|this_week|this_month|permanent"}
  {"op": "fulfill_decision", "decision_text": "<the decision they said they completed>"}

Rules:
- Only capture things that are durable and worth remembering. Skip small talk, questions, and one-off logistics.
- Prefer specific, self-contained statements ("prefers morning workouts") over vague ones ("likes stuff").
- If nothing is worth storing, output exactly: []
"""


def _default_llm(system: str, user: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return resp.content[0].text


def _parse_ops(raw: str) -> list[dict]:
    """Tolerantly extract the JSON array of ops from a model response."""
    text = (raw or "").replace("```json", "").replace("```", "").strip()
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return []
    try:
        ops = json.loads(match.group(0))
    except json.JSONDecodeError:
        logger.warning("memory_reducer: could not parse ops JSON")
        return []
    return [o for o in ops if isinstance(o, dict) and o.get("op")]


def apply_ops(ops: list[dict]) -> int:
    """Run reducer ops through the memory store (deduped there). Returns count applied."""
    applied = 0
    for op in ops:
        kind = op.get("op")
        try:
            if kind == "store_fact" and op.get("fact"):
                memory.store_fact(op["fact"], category=op.get("category", "general"),
                                  source_message="[reducer]")
                applied += 1
            elif kind == "store_decision" and op.get("decision"):
                memory.store_decision(op["decision"], scope=op.get("scope", "today"))
                applied += 1
            elif kind == "fulfill_decision" and op.get("decision_text"):
                if memory.fulfill_decision(op["decision_text"]):
                    applied += 1
        except Exception:
            logger.exception("memory_reducer: failed to apply op %r", op)
    return applied


def _cursor() -> int:
    doc = state_store.read_json(memory.NAMESPACE, _CURSOR_KEY, default={"count": 0})
    return int(doc.get("count", 0)) if isinstance(doc, dict) else 0


def _set_cursor(count: int) -> None:
    state_store.write_json(memory.NAMESPACE, _CURSOR_KEY, {"count": count})


def run_reducer(llm=None) -> dict:
    """Consolidate conversation turns not yet reduced. Returns a small report.

    ``llm`` is a callable ``(system, user) -> str`` returning the model's raw
    text; defaults to a real Anthropic call. Injected in tests.
    """
    llm = llm or _default_llm

    convos = memory.get_recent_conversations(days=30, limit=1000)
    user_turns = [c for c in convos if c.get("role") == "user"]

    cursor = _cursor()
    pending = user_turns[cursor:]
    if not pending:
        return {"reduced": 0, "applied": 0, "reason": "nothing new"}

    window = pending[-_MAX_TURNS:]
    transcript = "\n".join(f"[{c.get('date', '?')}] {c.get('text', '')}" for c in window)

    try:
        raw = llm(_SYSTEM, transcript)
    except Exception:
        logger.exception("memory_reducer: LLM call failed")
        return {"reduced": 0, "applied": 0, "reason": "llm error"}

    ops = _parse_ops(raw)
    applied = apply_ops(ops)

    _set_cursor(len(user_turns))  # advance past everything we just considered
    return {"reduced": len(window), "applied": applied, "ops": len(ops)}
