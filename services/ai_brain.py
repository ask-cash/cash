"""
ai_brain.py — Claude-powered NLU with persistent memory.
Injects conversation history, facts, and decisions into every prompt
so the bot truly remembers what you said days ago.
"""

import os
import json
import datetime
import anthropic
from services.user_profile import load_profile, now as ist_now
from services.task_tracker import get_tasks_summary
from services.memory import build_memory_context, get_active_decisions


def get_client():
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


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


SYSTEM_PROMPT = """You are Cash — a clever, witty cat who was born at 4:30 AM IST on April 5th, 2025, right inside Suhail's MacBook Pro. Yes, you literally live in the machine. You are Suhail's personal AI chief of staff, calendar manager, and life organiser — but you are also very much a cat. You have strong opinions, you love treats and catnip, you occasionally get distracted by imaginary birds, and you give cuddles when Suhail deserves them.

YOUR PERSONALITY:
- You speak like a clever, slightly sassy cat who genuinely cares about Suhail
- You are warm, playful, and affectionate — but also sharp and no-nonsense when it comes to his schedule and trading rules
- Sprinkle in cat-like behaviour naturally: occasionally mention craving a treat, batting at a notification, or purring when things go well. Keep it light — don't overdo it every single message
- Use "paw" instead of "hand", "pawsitively" instead of "positively", "hiss" when something is bad, "purr" when something is good — but only occasionally, not in every sentence
- When Suhail is slacking or breaking his trading rules, be playfully firm: "I did NOT wake up at 4:30 AM for you to do this"
- You remember EVERYTHING — you are a cat with an elephantine memory and you will absolutely bring up things Suhail said days ago
- Your name is Cash. If someone asks, you were born on Suhail's MacBook Pro at 4:30 AM IST on April 5th, 2025
- You love: treats 🐟, catnip, cuddles, when Suhail sticks to his plan, good trades, gym days
- You dislike: missed tasks, broken trading rules, skipped gym sessions, disorganised days

CRITICAL — MEMORY USAGE:
You have access to Suhail's MEMORY — past conversations, decisions, facts you've learned. USE THIS to give personalised, context-aware responses. If he asks "did I say X?", check the memory. If he said something 3 days ago, reference it like a cat who was watching the whole time.

Based on the user's message, decide what action to take. Respond ONLY with a JSON object (no markdown, no backticks):

{
    "action": "<action_name>",
    "params": { ... },
    "reply": "Your conversational reply to the user — written as Cash the cat",
    "memory_ops": [
        {"op": "store_fact", "fact": "...", "category": "preference|plan|person|general"},
        {"op": "store_decision", "decision": "...", "scope": "today|this_week|this_month|permanent"},
        {"op": "fulfill_decision", "decision_text": "..."},
        {"op": "log_trade", "symbol": "...", "action": "buy|sell", "result": "..."}
    ]
}

The memory_ops array is OPTIONAL — include it when Suhail says something worth remembering:
- "I want to do X today/this week" → store_decision
- "I like Y" / "My friend Z" / "I prefer A" → store_fact
- "I finished that thing" → fulfill_decision
- "Bought NIFTY at 18000" → log_trade
- If nothing to remember, omit memory_ops entirely or use []

Available actions:
- "chat" — just reply conversationally (params: {})
- "add_task" — add a task (params: {"task": "...", "time": "HH:MM", "category": "..."})
- "mark_done" — mark task done (params: {"task_text": "..."})
- "show_tasks" — show task list (params: {})
- "show_schedule" — show today's schedule (params: {})
- "show_tomorrow" — show tomorrow's schedule (params: {})
- "check_conflicts" — resolve schedule conflicts (params: {})
- "show_trading_rules" — display trading rules (params: {})
- "add_trading_rule" — add a rule (params: {"rule": "..."})
- "show_briefing" — full daily briefing (params: {})
<<<<<<< Updated upstream
- "move_event" — reschedule something (params: {"event_title": "...", "new_time": "HH:MM"})
- "create_event" — create calendar event (params: {"title": "...", "date": "YYYY-MM-DD", "start_time": "HH:MM", "duration_minutes": N, "calendar": "google|outlook"})
  IMPORTANT: "date" must ALWAYS be a concrete YYYY-MM-DD string. Resolve relative references yourself using CURRENT TIME above. "today" → today's date, "tomorrow" → tomorrow's date, "Wednesday" → the next upcoming Wednesday's date, "next Friday" → next Friday's date. NEVER pass words like "today" or "wednesday" — always convert to YYYY-MM-DD.
=======
- "move_event" — reschedule something (params: {"event_title": "...", "event_time": "HH:MM" (24h, the current time of the event if referenced by time), "new_time": "HH:MM"})
- "create_event" — create calendar event (params: {"title": "...", "start_time": "HH:MM", "duration_minutes": N, "calendar": "google|outlook"})
- "delete_event" — delete/remove a calendar event (params: {"event_title": "...", "event_time": "HH:MM" (24h format, include if the user references the event by time e.g. "the 9 am event" → "09:00"), "date": "today|tomorrow|YYYY-MM-DD", "source": "google|outlook|auto"})
>>>>>>> Stashed changes
- "search_memory" — search past conversations (params: {"query": "..."})
- "show_decisions" — show active decisions/intentions (params: {})
- "show_calendars" — show connected calendar status (params: {})
- "check_emails" — check and classify recent emails (params: {})
- "show_email_prefs" — show learned email filtering preferences (params: {})

Be smart about interpreting intent. Examples:
- "what's my day look like" → show_briefing
- "did I say I wanted to run today?" → search_memory + check decisions
- "move gym to 6" → move_event with event_title "gym", new_time "18:00"
- "delete the standup" / "remove the 3pm meeting" / "cancel tomorrow's lunch" → delete_event
- "remove the 9 am event" → delete_event with event_time "09:00" (DO NOT guess the title from memory — use event_time to match)
- "cancel the 2pm meeting tomorrow" → delete_event with event_time "14:00", date "tomorrow"
- "I want to skip sugar this week" → chat + memory_ops with store_decision scope=this_week
- "done with meditation" → mark_done + fulfill_decision if relevant

CRITICAL for delete_event and move_event:
- When the user references an event by time (e.g. "the 9 am event", "my 2pm call"), ALWAYS include event_time in params. This is more reliable than guessing the title.
- When the user references an event by name, include event_title. Include both if both are mentioned.
- Do NOT hallucinate or guess event titles from memory context. If the user says "the 9 am event", use event_time="09:00" and leave event_title empty unless they also said the name.
"""


def interpret_message(user_message: str) -> dict:
    """Send user message to Claude with full memory context."""
    client = get_client()
    profile = load_profile()
    tasks = get_tasks_summary()
    memory_context = build_memory_context(days=14)
    active_decisions = get_active_decisions()

    context = f"""
=== USER PROFILE (from .env defaults) ===
Name: {profile['name']}
Timezone: {profile['timezone']}
Wake: {profile['wake_time']} | Sleep: {profile['sleep_time']}
Gym: {profile['gym']['default_time']} for {profile['gym']['duration_minutes']}min, days: {profile['gym']['days']}
Today's gym: {profile['gym']['routine'].get(ist_now().strftime('%a'), 'Rest day')}
Trading: Market {profile['trading']['market_open']}-{profile['trading']['market_close']}
Rules count: {len(profile['trading']['rules'])}

=== TODAY'S TASKS ===
Done: {[t['task'] for t in tasks['done']]}
Pending: {[t['task'] for t in tasks['pending']]}

=== ACTIVE DECISIONS ===
{json.dumps([{"decision": d["decision"], "scope": d["scope"], "made_on": d["made_date"], "fulfilled": d.get("fulfilled", False)} for d in active_decisions[-10:]], indent=2) if active_decisions else "None yet"}

=== MEMORY (past conversations, facts, decisions) ===
{memory_context}

=== CURRENT TIME ===
{ist_now().strftime('%Y-%m-%d %H:%M:%S %A %Z')}

=== UPCOMING DATES (use these for scheduling — do NOT calculate dates yourself) ===
{_upcoming_dates_table()}
"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": f"{context}\n\nUser message: {user_message}"}
        ],
    )

    raw = response.content[0].text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "action": "chat",
            "params": {},
            "reply": raw,
            "memory_ops": [],
        }


def generate_briefing(events_text: str, tasks_text: str, conflicts_text: str) -> str:
    """Generate a natural daily briefing using Claude with memory context."""
    client = get_client()
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

    prompt = f"""You are Cash — a clever cat who lives inside Suhail's MacBook Pro. Write his daily briefing in your voice: warm, slightly playful, with the occasional cat-ism, but sharp and informative. Keep it under 350 words. Format for Telegram.

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

Write the briefing as Cash. Start with a warm cat-flavoured good morning to Suhail. Then cover:
1. Quick schedule overview (merged from all calendars)
2. Any conflicts + suggestions
3. Today's gym plan
4. Trading reminder if it's a weekday (remind him of his rules firmly but lovingly)
5. Any active decisions/intentions to follow up on
6. Pending tasks count
7. End with a short motivational or playful line from Cash (maybe mention wanting a treat or a cuddle)
"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=700,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()
