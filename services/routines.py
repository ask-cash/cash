"""
routines.py — bounded parallel fan-out for assistant-authored workflows.

Some tasks are naturally "do the same small thing across many items and combine
the answers" — score each of 20 options, summarise each of 15 docs. A routine
fans that out to many ephemeral sub-agents (leaf calls over the provider
abstraction), bounded by a hard **agent cap** and a **concurrency** limit, then
runs one **synthesis** step over the leaf outputs.

It is deliberately not a general script sandbox: routines are assistant-authored
(a fixed spec of leaf/synthesis prompts), run off the hot path, journal progress
to ``state_store`` so ``/routines`` can report status, and support cooperative
cancellation. The per-leaf model comes from the provider call sites
``routine_leaf`` / ``routine_synthesis``.

The LLM is injectable for tests; the default routes through
``services.providers.send_message``.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from dataclasses import dataclass, field

from services import state_store

logger = logging.getLogger(__name__)

NAMESPACE = "routines"
DEFAULT_MAX_AGENTS = 20
DEFAULT_CONCURRENCY = 5

STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_CANCELLED = "cancelled"
STATUS_ERROR = "error"


@dataclass
class Routine:
    """A fan-out spec. ``leaf_prompt`` uses ``{item}``; ``synthesis_prompt`` uses
    ``{results}`` (leave empty to skip synthesis)."""

    name: str
    items: list[str]
    leaf_prompt: str
    synthesis_prompt: str = ""
    system: str = ""
    call_site: str = "routine_leaf"
    synthesis_call_site: str = "routine_synthesis"
    max_agents: int = DEFAULT_MAX_AGENTS
    concurrency: int = DEFAULT_CONCURRENCY


# ---------------------------------------------------------------------------
# Journal + cancellation (state_store backed, best-effort)
# ---------------------------------------------------------------------------

def _job_key(rid: str) -> str:
    return f"job:{rid}"


def _cancel_key(rid: str) -> str:
    return f"cancel:{rid}"


def _write_journal(rid: str, data: dict) -> None:
    try:
        state_store.write_json(NAMESPACE, _job_key(rid), data)
    except Exception:
        logger.exception("[routines] journal write failed for %s", rid)


def get_status(rid: str) -> dict | None:
    """Current journal record for a routine, or None."""
    try:
        return state_store.read_json(NAMESPACE, _job_key(rid), default=None)
    except Exception:
        return None


def request_cancel(rid: str) -> None:
    """Ask a running routine to stop. Cooperative — checked between leaf calls."""
    try:
        state_store.write_json(NAMESPACE, _cancel_key(rid), True)
    except Exception:
        logger.exception("[routines] cancel write failed for %s", rid)


def _is_cancelled(rid: str) -> bool:
    try:
        return bool(state_store.read_json(NAMESPACE, _cancel_key(rid), default=False))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def _default_llm(system: str, user: str, call_site: str) -> str:
    from services import providers
    return providers.send_message(call_site, system=system or None, user=user)


async def _run_leaf(llm, system: str, prompt: str, call_site: str) -> str:
    # The provider call is blocking; run it in a thread so many leaves overlap.
    return await asyncio.to_thread(llm, system, prompt, call_site)


async def run_routine(routine: Routine, *, llm=None, routine_id: str | None = None) -> dict:
    """Fan out ``routine`` and return ``{id, status, results, synthesis}``.

    Enforces the agent cap (raises if ``items`` exceeds it), bounds in-flight
    leaves to ``concurrency``, journals progress, and honours a cancel request.
    """
    rid = routine_id or uuid.uuid4().hex
    total = len(routine.items)
    if total > routine.max_agents:
        raise ValueError(
            f"routine '{routine.name}' requests {total} agents > cap {routine.max_agents}")

    llm = llm or _default_llm
    state = {"id": rid, "name": routine.name, "total": total, "done": 0,
             "status": STATUS_RUNNING}
    _write_journal(rid, state)

    sem = asyncio.Semaphore(max(1, routine.concurrency))
    results: list[str | None] = [None] * total
    aborted = threading.Event()
    progress_lock = asyncio.Lock()

    async def worker(i: int, item: str) -> None:
        if aborted.is_set() or _is_cancelled(rid):
            aborted.set()
            return
        async with sem:
            if aborted.is_set() or _is_cancelled(rid):
                aborted.set()
                return
            prompt = routine.leaf_prompt.format(item=item)
            results[i] = await _run_leaf(llm, routine.system, prompt, routine.call_site)
        async with progress_lock:
            state["done"] += 1
            _write_journal(rid, dict(state))

    await asyncio.gather(*(worker(i, it) for i, it in enumerate(routine.items)))

    leaf_results = [r for r in results if r is not None]

    if aborted.is_set() or _is_cancelled(rid):
        state["status"] = STATUS_CANCELLED
        _write_journal(rid, dict(state))
        return {"id": rid, "status": STATUS_CANCELLED, "results": leaf_results, "synthesis": None}

    synthesis = None
    if routine.synthesis_prompt:
        joined = "\n".join(f"- {r}" for r in leaf_results)
        synthesis = await _run_leaf(
            llm, routine.system,
            routine.synthesis_prompt.format(results=joined),
            routine.synthesis_call_site,
        )

    state["status"] = STATUS_DONE
    _write_journal(rid, dict(state))
    return {"id": rid, "status": STATUS_DONE, "results": leaf_results, "synthesis": synthesis}


def run_routine_blocking(routine: Routine, *, llm=None, routine_id: str | None = None) -> dict:
    """Synchronous entry point for callers not already in an event loop (e.g. a
    worker thread). Wraps ``run_routine`` in ``asyncio.run``."""
    return asyncio.run(run_routine(routine, llm=llm, routine_id=routine_id))
