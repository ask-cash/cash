

# 😼 Cash — Suhail's Personal AI Cat Assistant

> *"I was born at 4:30 AM IST on April 5th, inside Suhail's MacBook Pro. I literally live here. It's warm and I'm not leaving."*

**Cash** is a Telegram bot with a personality. She's a cat. She manages Suhail's calendar (Google + Outlook), tracks daily tasks, enforces trading rules, resolves schedule conflicts, **remembers everything**, and sends daily briefings — all with the energy of a cat who has been awake since 4:30 AM and has opinions about it.

---

## What Cash Does

- **Remembers everything** — "I want to skip sugar this week" → she'll bring it up 3 days later
- **Multi-calendar** — merges Google Calendar + Outlook into one unified view
- **Smart scheduling** — auto-resolves conflicts (shifts gym when meetings overlap, suggests alternatives)
- **Daily briefings** — morning wake-up + evening wrap-up, sent automatically in Cash's voice
- **Task tracking** — todo list with automatic rollover for unfinished tasks
- **Trading rules** — recites your rules before market open, calls you out if you break discipline
- **Meeting tracking** — pings you if a meeting ended and you haven't confirmed attendance
- **Natural language** — just talk to her, Claude figures out intent and Cash responds in character

---

## Setup

### Step 1 — Create a Telegram Bot

1. Message [@BotFather](https://t.me/BotFather) on Telegram → `/newbot`
2. Follow the prompts and copy your **bot token**
3. Start a chat with your new bot, then get your **Telegram user ID** from [@userinfobot](https://t.me/userinfobot)

### Step 2 — Get an Anthropic API Key

Sign up at [console.anthropic.com](https://console.anthropic.com) and create an API key.

### Step 3 — Configure `.env`

```bash
cp .env.example .env
```

Open `.env` and fill in everything — your name, timezone, wake/sleep times, gym schedule, diet, trading rules, and default daily tasks. **You only configure this once.** Cash reads everything from here.

Key fields:

```env
TELEGRAM_BOT_TOKEN=your_token_here
ANTHROPIC_API_KEY=your_claude_api_key
YOUR_TELEGRAM_USER_ID=your_numeric_id   # bot is private — only you can use it

USER_NAME=Suhail
TIMEZONE=Asia/Kolkata
WAKE_TIME=06:30
SLEEP_TIME=23:00
```

### Step 4 — Set Up Google Calendar

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → Create a new project
2. Enable the **Google Calendar API**
3. Create **OAuth 2.0 credentials** (Desktop app type) → Download as `credentials.json` into the project root
4. Run the one-time auth:

```bash
python scripts/auth_google.py
```

This opens a browser, you sign in, and `token.json` is saved. Done.

### Step 5 — Set Up Outlook Calendar (optional)

If you use Microsoft/Outlook calendar:

1. Go to [Azure Portal](https://portal.azure.com) → **App registrations** → New registration
2. Add redirect URI: `http://localhost:8400`
3. Under **API permissions**, add: `Calendars.ReadWrite`, `User.Read`
4. Create a client secret under **Certificates & secrets**
5. Add `OUTLOOK_CLIENT_ID`, `OUTLOOK_CLIENT_SECRET`, `OUTLOOK_TENANT_ID` to your `.env`
6. Run:

```bash
python scripts/auth_outlook.py
```

This uses device code flow — works on servers too. Follow the printed instructions.

### Step 6 — Install Dependencies & Run

```bash
pip install -r requirements.txt
python main.py
```

Cash is now alive and watching.

---


## Commands


| Command        | What Cash does                                        |
| -------------- | ----------------------------------------------------- |
| `/start`       | Cash introduces herself and shows connected calendars |
| `/briefing`    | Full daily briefing — schedule, tasks, gym, trading   |
| `/tasks`       | Today's task list with status                         |
| `/done <task>` | Mark a task as done (by name or ID)                   |
| `/add <task>`  | Add a new task to today's list                        |
| `/schedule`    | Today's calendar (all connected sources)              |
| `/conflicts`   | Detect and resolve schedule conflicts                 |
| `/rules`       | Your trading rules                                    |
| `/decisions`   | Active intentions and decisions Cash is tracking      |
| `/memory`      | Everything Cash remembers about you                   |
| `/calendars`   | Status of connected calendar sources                  |
| `/settings`    | Your current profile loaded from `.env`               |


---

## Natural Language Examples

Just talk to Cash naturally. Some examples:

```
"what's my day look like"            → full briefing
"move gym to 6pm"                    → reschedules the event
"I want to eat clean this week"      → stored as a weekly decision
"did I say I'd call mom?"            → searches conversation memory
"done with meditation"               → marks task done + fulfills decision
"add buy groceries to my list"       → adds task
"what are my trading rules?"         → shows rules
"I bought NIFTY at 22500"           → logged to trading journal
"what did I say yesterday?"          → recalls recent memory
"create a meeting at 3pm for 1 hour" → creates calendar event
```

---

## How Memory Works

Every message is logged to `user_data/memory/conversations.jsonl`. Cash also extracts and stores:


| What you say                     | What gets stored                                     |
| -------------------------------- | ---------------------------------------------------- |
| "I want to..." / "today I'll..." | Decision with expiry (today / this week / permanent) |
| "I like..." / "my friend X..."   | Permanent fact about you                             |
| "I finished X"                   | Decision marked as fulfilled                         |
| "Bought NIFTY at 18000"          | Trade entry in journal                               |


Before every response, Cash injects your recent memory, active decisions, and learned facts into Claude's context — so she genuinely knows what you said 5 days ago and references it naturally.

---

## Cash's Personality

Cash is not a generic assistant. She is a cat.

- **Born:** April 5th, 4:30 AM IST — inside Suhail's MacBook Pro
- **Likes:** treats, catnip, cuddles, when Suhail sticks to his plan, good trades, gym days
- **Dislikes:** missed tasks, broken trading rules, skipped gym sessions, disorganised days
- **Catchphrase when Suhail slacks:** *"I did NOT wake up at 4:30 AM for this."*

Her tone is warm and caring but she will absolutely call you out. She remembers everything, and she's not shy about bringing it up.