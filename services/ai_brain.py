"""
ai_brain.py — Claude-powered NLU with persistent memory.
Injects conversation history, facts, and decisions into every prompt
so the bot truly remembers what you said days ago.
"""

from __future__ import annotations

import re
import json
import logging
import datetime
from services import persona
from services import providers
from services.user_profile import load_profile, now as ist_now
from services.task_tracker import get_tasks_summary
from services.memory import build_memory_context, get_active_decisions
from services import memory_brief, memory_recall
from services.files import (
    build_files_context,
    build_claude_content_block,
)

logger = logging.getLogger(__name__)


def _upcoming_dates_table() -> str:
    """Generate a lookup table of the next 14 days so Claude doesn't have to do date math."""
    lines = []
    base = ist_now().date()
    for i in range(14):
        d = base + datetime.timedelta(days=i)
        label = "today" if i == 0 else "tomorrow" if i == 1 else ""
        day_name = d.strftime("%A")
        lines.append(f"  {day_name} = {d.isoformat()}" + (f"  ({label})" if label else ""))
    return "\n".join(lines)


# The behavioural contract is now assembled per turn from three parts:
#   1. _CONTRACT_PREAMBLE — who you're addressing, memory rules, the JSON protocol
#   2. the "Available actions" list, PROJECTED from the active skill packs
#      (services.skills) so capabilities are declarative + individually flaggable
#   3. _CONTRACT_RULES — the cross-cutting interpretation + CRITICAL rules
# Cash's *voice* is composed separately from services.persona (single source of
# truth); every part here is voice-free.
_CONTRACT_PREAMBLE = """IMPORTANT — WHO YOU'RE TALKING TO: Always address the user by the name shown in the USER PROFILE section of the context. Never assume their name (it is NOT always "Suhail"). When you need to refer to them, use that name or "you".

You care about them sticking to their plan — disciplined trades, consistent gym sessions, a well-organised day — and you flag missed tasks, broken trading rules, skipped gym sessions, and disorganised days.

CRITICAL — MEMORY USAGE:
You have access to the user's MEMORY — past conversations, decisions, facts you've learned. USE THIS to give personalised, context-aware responses. If they ask "did I say X?", check the memory. If they said something 3 days ago, reference it precisely — you've been keeping track the whole time.

Based on the user's message, decide what action to take. Respond ONLY with a JSON object (no markdown, no backticks):

{
    "action": "<action_name>",
    "params": { ... },
    "reply": "Your conversational reply to the user — written as Cash, in her own voice (see the persona block above)",
    "memory_ops": [
        {"op": "store_fact", "fact": "...", "category": "preference|plan|person|general"},
        {"op": "store_decision", "decision": "...", "scope": "today|this_week|this_month|permanent"},
        {"op": "fulfill_decision", "decision_text": "..."},
        {"op": "log_trade", "symbol": "...", "action": "buy|sell", "result": "..."}
    ]
}

The memory_ops array is OPTIONAL — include it when the user says something worth remembering:
- "I want to do X today/this week" → store_decision
- "I like Y" / "My friend Z" / "I prefer A" → store_fact
- "I finished that thing" → fulfill_decision
- "Bought NIFTY at 18000" → log_trade
- If nothing to remember, omit memory_ops entirely or use []

Available actions:"""


_CONTRACT_RULES = """Be smart about interpreting intent. Examples:
- "what's my day look like" → show_briefing
- "did I say I wanted to run today?" → search_memory + check decisions
- "move gym to 6" → move_event with event_title "gym", new_time "18:00"
- "shift tomorrow's 6pm run to today" → move_event with event_title "run", event_time "18:00", date "tomorrow", new_date "today" (event is CURRENTLY on tomorrow, so date="tomorrow"; it moves TO today, so new_date="today")
- "move the standup to July 8 at 4pm" → move_event with event_title "standup", new_date "2026-07-08", new_time "16:00"
- "what's on July 6" / "check July 6 events" / "show me the 6th" → show_date with date "2026-07-06"
- "delete the standup" / "remove the 3pm meeting" / "cancel tomorrow's lunch" → delete_event
- "remove the 9 am event" → delete_event with event_time "09:00" (DO NOT guess the title from memory — use event_time to match)
- "cancel the 2pm meeting tomorrow" → delete_event with event_time "14:00", date "tomorrow"
- "I want to skip sugar this week" → chat + memory_ops with store_decision scope=this_week
- "done with meditation" → mark_done + fulfill_decision if relevant
- "create a braces change every 14 days, set 1 to 13, starting June 29" → create_recurring_events with title_template "Change Braces Set - {n}", start_date "2026-06-29", interval_days 14, count 13
- "remind me to call mom at 6pm" → set_reminder with text "Call mom", date today, time "18:00"
- "ping me in 30 minutes to stretch" → set_reminder with text "Stretch", date today, time = CURRENT TIME + 30 min
- "what reminders do I have?" → show_reminders

CRITICAL — NEVER CLAIM YOU CREATED MULTIPLE EVENTS UNLESS YOU USED create_recurring_events:
- A single create_event creates EXACTLY ONE event. You cannot create a series with it.
- If the user wants more than one event at an interval, you MUST use create_recurring_events in a SINGLE response. Do NOT promise to "create them one by one" and do NOT say a batch is done when you only emitted one create_event.
- Never invent a list of created events in "reply". Only the action result is authoritative.

CRITICAL — TIME AWARENESS:
- Always reason relative to CURRENT TIME (shown in context). An event whose start time is BEFORE CURRENT TIME has already happened — refer to it in the past ("your 8:30 PM gym is done", "earlier today"), NEVER as "tonight", "coming up", or "later".
- Only call something "tonight" / "upcoming" / "next" if its time is actually AFTER CURRENT TIME.
- When the user says it's late or events should be over, trust that and treat today's earlier events as completed.

CRITICAL — DO NOT FABRICATE STATE:
- Do NOT invent a "summary of everything set up today". Only state what THIS conversation's actions actually did, or what is explicitly in the context above.
- create_event/create_recurring_events do NOT set reminders/notifications. NEVER claim an event has "a 1-hour reminder" or "reminder at 5 PM" — that feature does not exist.
- If you are not sure an event exists or what time it is, use show_schedule / show_briefing to check rather than guessing. Do not assert calendar contents you have not verified.

CRITICAL — COLD START / NO ROUTINE ON FILE:
- If the USER PROFILE says "ROUTINE: NONE ON FILE", you genuinely do NOT know their schedule, gym, work/study hours, sleep, or trading. NEVER invent defaults or claim you "have" a routine — saying you have a 7:30 gym or 9:15 market open when nothing is on file is a serious error.
- For a new or routine-less person: warmly introduce yourself, then ask about their day-to-day and how they'd like help. One step at a time — don't interrogate.
- Make it generic to ANY audience (student, founder, parent, trader, 9-to-5, shift worker). A good first ask: "I don't have your routine yet — tell me about a typical day: when you usually wake and sleep, your work/study hours, anything recurring (gym, classes, meetings, market hours), and what you'd like me to help you stay on top of."
- When they share details, capture them with update_profile (ONLY the fields they actually gave) and confirm what you saved.
- As part of first-time setup, also invite them to connect their calendar so you can see and manage their schedule. Follow the CURRENT SURFACE guidance below for the correct command or dashboard navigation. Do this early — a connected calendar is core to how you help.
- NEVER claim to see a schedule/events when the calendar isn't connected. If asked about the calendar and it isn't connected, say it isn't connected yet and use the CURRENT SURFACE connection guidance (the action result is authoritative on this).

CRITICAL for delete_event and move_event:
- When the user references an event by time (e.g. "the 9 am event", "my 2pm call"), ALWAYS include event_time in params. This is more reliable than guessing the title.
- When the user references an event by name, include event_title. Include both if both are mentioned.
- Do NOT hallucinate or guess event titles from memory context. If the user says "the 9 am event", use event_time="09:00" and leave event_title empty unless they also said the name.
"""


def _build_action_contract(surface: str = "telegram") -> str:
    """Assemble the behavioural contract, projecting the action list from the
    active skill packs (services.skills). Called per turn so a pack toggled off
    disappears from the prompt entirely."""
    from services import platform_commands, skills

    return (
        f"{_CONTRACT_PREAMBLE}\n"
        f"{skills.build_action_contract()}\n\n"
        f"{_CONTRACT_RULES}\n\n"
        f"{platform_commands.prompt_block(surface)}"
    )


def _build_system_prompt(surface: str = "telegram") -> str:
    """Compose Cash's owner-mode voice (from services.persona) with the action
    contract. Called per turn so the persisted SOUL/NOW overlays are picked up."""
    return f"{persona.persona_system_block('owner')}\n\n{_build_action_contract(surface)}"


def _profile_block(profile: dict) -> str:
    """Render the USER PROFILE context — only what the user has actually told us.

    When no routine is on file, say so explicitly so the model asks for it
    instead of inventing defaults.
    """
    from services.user_profile import has_routine

    name = profile.get("name") or "(unknown — ask them their name)"
    lines = [f"Name: {name}", f"Timezone: {profile.get('timezone') or '(unknown)'}"]

    if not has_routine(profile):
        lines.append(
            "ROUTINE: NONE ON FILE. You have ZERO knowledge of this person's schedule, "
            "sleep, gym, work/study hours, or trading. Do NOT assume or invent any. "
            "Offer to set it up and ask for their routine (see COLD START rule)."
        )
        return "\n".join(lines)

    gym = profile.get("gym", {}) or {}
    trading = profile.get("trading", {}) or {}
    if profile.get("wake_time") or profile.get("sleep_time"):
        lines.append(f"Wake: {profile.get('wake_time') or '?'} | Sleep: {profile.get('sleep_time') or '?'}")
    if gym.get("default_time") or gym.get("days"):
        lines.append(f"Gym: {gym.get('default_time') or '?'} ({gym.get('duration_minutes') or '?'}min), days: {gym.get('days') or []}")
        today_gym = (gym.get("routine") or {}).get(ist_now().strftime('%a'))
        if today_gym:
            lines.append(f"Today's gym: {today_gym}")
    if trading.get("market_open") or trading.get("rules"):
        lines.append(
            f"Trading: {trading.get('market_open') or '?'}-{trading.get('market_close') or '?'}, "
            f"rules on file: {len(trading.get('rules') or [])}"
        )
    return "\n".join(lines)


def interpret_message(
    user_message: str,
    calendar_context: str = "",
    *,
    surface: str = "telegram",
    conversation_history: str = "",
    attachment_records: list[dict] | None = None,
    model: str | None = None,
) -> dict:
    """Send user message to Claude with full memory context.

    ``calendar_context`` is the user's real today/tomorrow events (injected by the
    caller, which owns the live calendar client). Ground time-relative requests
    like "remind me an hour before my dentist appointment" on THIS, never a guess.
    """
    profile = load_profile()
    tasks = get_tasks_summary()
    # Memory v2: a bounded, freshly-compiled brief every turn (not a raw log
    # dump), plus gated archive recall only when the message reaches into the past.
    memory_context = memory_brief.build_brief()
    recall_block = memory_recall.recall_block(user_message)
    active_decisions = get_active_decisions()
    attachment_records = attachment_records or []
    uploads_context = (
        "Attachments are scoped to this dashboard conversation."
        if surface == "dashboard"
        else build_files_context(limit=5)
    )

    context = f"""
=== USER PROFILE ===
{_profile_block(profile)}

=== CALENDAR (real events — use these exact times for anything time-relative) ===
{calendar_context or "(not provided)"}

=== TODAY'S TASKS ===
Done: {[t['task'] for t in tasks['done']]}
Pending: {[t['task'] for t in tasks['pending']]}

=== ACTIVE DECISIONS ===
{json.dumps([{"decision": d["decision"], "scope": d["scope"], "made_on": d["made_date"], "fulfilled": d.get("fulfilled", False)} for d in active_decisions[-10:]], indent=2) if active_decisions else "None yet"}

=== MEMORY BRIEF (current, time-relevant context) ===
{memory_context}
{recall_block}

=== CURRENT CONVERSATION (oldest to newest; reference only) ===
{conversation_history or "(No earlier turns.)"}

=== RECENT UPLOADS (most recent first) ===
{uploads_context}

=== CURRENT TIME ===
{ist_now().strftime('%Y-%m-%d %H:%M:%S %A %Z')}

=== UPCOMING DATES (use these for scheduling — do NOT calculate dates yourself) ===
{_upcoming_dates_table()}
"""
    user_text = f"{context}\n\nUser message: {user_message or '(The user attached media without a typed message.)'}"
    messages = None
    if attachment_records:
        from services import attachments as dashboard_attachments

        blocks = []
        for record in attachment_records:
            block = dashboard_attachments.build_claude_content_block(record)
            if block is not None:
                blocks.append(block)
            else:
                blocks.append({
                    "type": "text",
                    "text": (
                        f"Attachment: {record.get('name') or record.get('original_name') or 'file'} "
                        f"({record.get('mimeType') or record.get('mime_type') or 'unknown type'}). "
                        "Its contents are not directly readable."
                    ),
                })
        blocks.append({"type": "text", "text": user_text})
        messages = [{"role": "user", "content": blocks}]

    provider_result = providers.send_message_result(
        "owner_brain",
        system=_build_system_prompt(surface),
        messages=messages,
        user=None if messages is not None else user_text,
        model=model,
        # Dashboard model entitlements are specifically for Anthropic's managed
        # Claude catalog; a tenant-wide fallback provider must not reinterpret
        # those IDs through another API.
        provider="anthropic" if surface == "dashboard" else None,
    )
    raw = provider_result.text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    # Isolate the JSON object even if the model wrapped it in prose.
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    candidate = match.group(0) if match else raw

    # strict=False tolerates literal newlines inside string values — the model
    # often puts multi-line replies (e.g. a bulleted schedule) in "reply", which
    # is invalid strict JSON and previously dumped the whole envelope to the user.
    try:
        parsed = json.loads(candidate, strict=False)
    except json.JSONDecodeError:
        logger.warning("interpret_message: could not parse model output as JSON; treating as chat")
        parsed = {
            "action": "chat",
            "params": {},
            "reply": raw,
            "memory_ops": [],
        }
    if not isinstance(parsed, dict):
        parsed = {
            "action": "chat",
            "params": {},
            "reply": raw,
            "memory_ops": [],
        }
    parsed["_provider_usage"] = {
        "inputTokens": provider_result.input_tokens,
        "outputTokens": provider_result.output_tokens,
        "modelId": provider_result.model or model or "",
    }
    return parsed


def generate_briefing(
    events_text: str,
    tasks_text: str,
    conflicts_text: str,
    *,
    surface: str = "telegram",
) -> str:
    """Generate a natural daily briefing using Claude with memory context."""
    profile = load_profile()
    memory_context = build_memory_context(days=3)
    active_decisions = get_active_decisions()

    trading = profile.get("trading", {})
    gym = profile.get("gym", {})
    diet = profile.get("diet", {})
    day_name = ist_now().strftime("%a")

    decisions_text = ""
    if active_decisions:
        decisions_text = "ACTIVE DECISIONS/INTENTIONS:\n"
        for d in active_decisions[-5:]:
            decisions_text += f"  - {d['decision']} ({d['scope']}, made {d['made_date']})\n"

    user_name = profile.get("name") or "there"
    from services import platform_commands

    format_instruction = (
        "Format it for a clean web chat response."
        if surface == "dashboard"
        else "Format it for Telegram."
    )
    prompt = f"""{persona.persona_system_block('owner')}

Now write {user_name}'s daily briefing in your voice. Keep it under 350 words. {format_instruction}
{platform_commands.prompt_block(surface)}

SCHEDULE:
{events_text}

TASKS:
{tasks_text}

CONFLICTS:
{conflicts_text}

GYM TODAY: {gym.get('routine', {}).get(day_name, 'Rest day')} at {gym.get('default_time', '?')}
DIET: {len(diet.get('meals', []))} meals planned, {diet.get('water_goal_liters', 3)}L water goal
SUPPLEMENTS: {', '.join(diet.get('supplements', []))}
TRADING: Market {trading.get('market_open', '?')}-{trading.get('market_close', '?')}, pre-review at {trading.get('pre_market_review_time', '?')}

{decisions_text}

RECENT MEMORY:
{memory_context}

Write the briefing as Cash — in character. Start with a short good morning to {user_name} in your voice. Then cover:
1. Quick schedule overview (merged from all calendars)
2. Any conflicts + suggestions
3. Today's gym plan
4. Trading reminder if it's a weekday (remind them of their rules firmly but supportively)
5. Any active decisions/intentions to follow up on
6. Pending tasks count
7. End with a short, motivating line that keeps them focused on the day ahead
"""

    return providers.send_message("briefing", user=prompt).strip()


def answer_about_file(record: dict, question: str, *, surface: str = "telegram") -> str:
    """Send an uploaded file to Claude along with the user's question.

    Supports PDFs (document block), images, and text files. For unsupported
    types, falls back to a filename-only prompt so Cash can at least respond.
    """
    question = (question or "Summarise this file").strip()

    block = build_claude_content_block(record)
    if block is None:
        user_content = [{
            "type": "text",
            "text": (
                f"The user uploaded a file called '{record.get('name')}' "
                f"(type: {record.get('mime_type') or 'unknown'}), but its contents "
                f"can't be read directly. Here is their question: {question}\n\n"
                f"Reply as Cash — in your voice; acknowledge the file by name and answer as best you can."
            ),
        }]
    else:
        user_content = [
            block,
            {"type": "text", "text": f"File: {record.get('name')}\n\nUser's ask: {question}\n\nReply as Cash — in your voice, concise and useful."},
        ]

    return providers.send_message(
        "file_answer",
        system=(
            f"{persona.persona_system_block('owner')}\n\n"
            "Answer the user's question about their file in your voice. Keep it concise "
            f"and appropriate for the {surface} surface."
        ),
        messages=[{"role": "user", "content": user_content}],
    ).strip()
