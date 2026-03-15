# Discord Productivity Bot — Implementation Plan

## Tech Stack

| Component | Tool | Why |
|-----------|------|-----|
| Bot framework | `discord.py` | Mature Python library, good async support |
| AI brain | Anthropic Python SDK (`anthropic`) | Claude understands natural language commands |
| Database | SQLite (via `aiosqlite`) | Zero-config, file-based, async-compatible |
| Scheduler | `APScheduler` | Cron-like and one-off reminders in Python |
| Email | `google-api-python-client` + OAuth2 | Read Gmail inbox programmatically |
| Environment | `python-dotenv` | Keep API keys out of source code |

---

## Project Structure

```
productivity-bot/
├── bot.py                  # Entry point, bot startup
├── config.py               # Load env vars, constants
├── database.py             # SQLite schema + CRUD helpers
├── cogs/
│   ├── links.py            # Save/retrieve links
│   ├── todos.py            # Daily to-do lists
│   ├── bucket_list.py      # Long-term goals
│   ├── journal.py          # Daily progress logging
│   ├── reminders.py        # Timed + contextual reminders
│   └── notifications.py    # Gmail + Discord notification checks
├── services/
│   ├── claude_service.py   # Wrapper around Anthropic API
│   ├── gmail_service.py    # Gmail API integration
│   └── scheduler_service.py# APScheduler setup
├── .env                    # API keys (never commit this)
├── requirements.txt
└── README.md
```

---

## Phase 1 — Foundation (Day 1–2)

### Step 1: Create your Discord bot

1. Go to https://discord.com/developers/applications
2. Click **New Application**, name it (e.g., "ProductivityBot")
3. Go to the **Bot** tab → click **Add Bot**
4. Copy the **Bot Token** (you'll need this)
5. Under **Privileged Gateway Intents**, enable:
   - Message Content Intent
   - Server Members Intent (optional, for DM support)
6. Go to **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Permissions: Send Messages, Read Message History, Embed Links
7. Copy the generated URL and open it in your browser to invite the bot to your server

### Step 2: Set up the project

```bash
mkdir productivity-bot && cd productivity-bot
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install discord.py anthropic aiosqlite apscheduler python-dotenv
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

Create your `.env` file:

```env
DISCORD_TOKEN=your_discord_bot_token
ANTHROPIC_API_KEY=your_anthropic_api_key
BOT_CHANNEL_ID=123456789  # The channel ID where your bot lives
```

### Step 3: Create the database schema

In `database.py`, create these tables:

```
links
├── id (INTEGER PRIMARY KEY)
├── url (TEXT)
├── title (TEXT, optional — Claude can summarize it)
├── tags (TEXT, comma-separated)
├── saved_at (TIMESTAMP)
└── read (BOOLEAN, default false)

todos
├── id (INTEGER PRIMARY KEY)
├── date (TEXT, e.g. "2025-03-14")
├── task (TEXT)
├── completed (BOOLEAN)
├── notes (TEXT, for end-of-day reflection)
└── created_at (TIMESTAMP)

bucket_list
├── id (INTEGER PRIMARY KEY)
├── goal (TEXT)
├── category (TEXT, e.g. "career", "health", "travel")
├── status (TEXT: "not_started", "in_progress", "done")
├── added_at (TIMESTAMP)
└── completed_at (TIMESTAMP, nullable)

journal
├── id (INTEGER PRIMARY KEY)
├── date (TEXT)
├── entry (TEXT — your progress notes)
├── mood (TEXT, optional)
└── created_at (TIMESTAMP)

reminders
├── id (INTEGER PRIMARY KEY)
├── message (TEXT)
├── remind_at (TIMESTAMP, nullable — for timed reminders)
├── context (TEXT, nullable — e.g. "heading_out", "morning", "evening")
├── recurring (BOOLEAN)
├── fired (BOOLEAN)
└── created_at (TIMESTAMP)
```

### Step 4: Write the basic bot skeleton

In `bot.py`:

```python
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    # Initialize database here
    # Start APScheduler here

# Load cogs
async def main():
    async with bot:
        await bot.load_extension("cogs.links")
        await bot.load_extension("cogs.todos")
        # ... load other cogs
        await bot.start(os.getenv("DISCORD_TOKEN"))

import asyncio
asyncio.run(main())
```

At this point: **test that the bot comes online and responds to a basic command.**

---

## Phase 2 — Core Features (Day 3–5)

### Step 5: Links manager (`cogs/links.py`)

Commands to implement:
- `!save <url> [tags]` — Save a link with optional tags
- `!links` — Show all unread links
- `!links read` — Show read links
- `!read <id>` — Mark a link as read

**Claude integration**: When saving a link, optionally send the URL to Claude and ask it to generate a short summary/title. This makes your reading list much more useful.

### Step 6: Daily to-do list (`cogs/todos.py`)

Commands:
- `!todo add <task>` — Add a task for today
- `!todo` or `!today` — Show today's task list
- `!todo done <id>` — Mark a task as complete
- `!todo date 2025-03-20` — View tasks for a specific date

**Format example** (what the bot sends back):

```
📋 Today's Tasks (March 14, 2025)
━━━━━━━━━━━━━━━━━━━━━━━
✅ 1. Review PR for backend refactor
⬜ 2. Write unit tests for auth module
⬜ 3. Call dentist to reschedule
━━━━━━━━━━━━━━━━━━━━━━━
Progress: 1/3 (33%)
```

### Step 7: Bucket list (`cogs/bucket_list.py`)

Commands:
- `!goal add <goal> [category]` — Add a long-term goal
- `!goals` — Show all goals grouped by category
- `!goal progress <id>` — Mark as in-progress
- `!goal done <id>` — Mark as complete

### Step 8: Journal / progress tracking (`cogs/journal.py`)

Commands:
- `!log <entry>` — Log a progress entry for today
- `!reflect` — Bot asks Claude to summarize your day based on completed/incomplete todos and journal entries
- `!journal [date]` — View journal entries for a date

**Claude integration**: At end of day (or on `!reflect`), Claude reads your todo completion status + journal entries and generates a brief reflection like:

> "You completed 4/6 tasks today. The two you missed were both related to the backend migration — you noted that you were blocked waiting on the API spec. Consider following up with the team tomorrow morning."

---

## Phase 3 — Reminders (Day 6–7)

### Step 9: Timed reminders (`cogs/reminders.py`)

Commands:
- `!remind at 9pm Call Sarah about the project` — Time-based reminder
- `!remind before heading_out Bring the package` — Context-based reminder
- `!remind morning Check email and Slack` — Morning context
- `!heading out` or `!leaving` — Triggers all "heading_out" context reminders
- `!reminders` — List all active reminders

**How timed reminders work:**
1. User says `!remind at 9pm Call Sarah`
2. Bot parses the time (use Claude for natural language → datetime parsing)
3. Stores in the `reminders` table with `remind_at` set
4. APScheduler picks it up and fires a DM or channel message at 9pm

**How contextual reminders work:**
1. User says `!remind before heading_out Bring the package`
2. Stored with `context = "heading_out"`, no `remind_at`
3. When user says `!heading out`, bot queries all unfired reminders with that context
4. Sends them all at once

**APScheduler setup** (`services/scheduler_service.py`):

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

scheduler = AsyncIOScheduler(
    jobstores={"default": SQLAlchemyJobStore(url="sqlite:///jobs.db")}
)
```

This persists scheduled jobs to disk so they survive bot restarts.

---

## Phase 4 — Notifications (Day 8–9)

### Step 10: Gmail integration (`services/gmail_service.py`)

1. Go to https://console.cloud.google.com
2. Create a new project
3. Enable the **Gmail API**
4. Create **OAuth 2.0 credentials** (Desktop app type)
5. Download `credentials.json` into your project
6. On first run, complete the OAuth flow to get `token.json`

The bot checks for unread emails matching your criteria:
- `!email check` — Show unread email count + subjects from important senders
- You can configure a list of "important senders" in your `.env`

### Step 11: Discord notification check (`cogs/notifications.py`)

Using discord.py's built-in capabilities:
- `!mentions` — Check recent mentions across your servers
- `!notifications` — Combined: unread emails + Discord mentions

---

## Phase 5 — Claude as the Brain (Day 10–12)

### Step 12: Natural language command routing

Instead of rigid `!command` syntax, let users type naturally and have Claude figure out the intent. Set up a fallback `on_message` handler:

```python
@bot.event
async def on_message(message):
    # Try prefix commands first
    await bot.process_commands(message)

    # If no command matched and message is in the bot channel:
    if message.channel.id == BOT_CHANNEL_ID and not message.author.bot:
        # Send to Claude with system prompt explaining available actions
        response = await claude_service.route_command(message.content)
        # Execute the appropriate function based on Claude's response
```

**System prompt for Claude** (in `services/claude_service.py`):

```
You are a productivity assistant Discord bot. Given the user's message,
determine what action to take. Respond with JSON:

{
  "action": "add_todo" | "list_todos" | "save_link" | "add_reminder" | ...
  "parameters": { ... extracted parameters ... }
}

Available actions: add_todo, list_todos, complete_todo, save_link,
list_links, add_goal, list_goals, log_journal, reflect, set_reminder,
check_context_reminders, check_email, check_mentions, general_chat

Examples:
- "remind me at 9pm to call Sarah" →
  {"action": "set_reminder", "parameters": {"time": "21:00", "message": "Call Sarah"}}
- "I'm heading out now, any reminders?" →
  {"action": "check_context_reminders", "parameters": {"context": "heading_out"}}
- "what do I need to do today?" →
  {"action": "list_todos", "parameters": {"date": "today"}}
```

This is the key integration — it turns your bot from a rigid command parser into a conversational assistant.

---

## Phase 6 — Polish & Deploy (Day 13–14)

### Step 13: Quality of life improvements

- **Embed formatting**: Use `discord.Embed` for rich responses (colors, fields, thumbnails)
- **Error handling**: Wrap all commands in try/except, send friendly error messages
- **Help command**: Override the default `!help` to list all features nicely
- **Daily summary**: Schedule a morning message summarizing today's todos and pending reminders
- **Weekly review**: Every Sunday, Claude summarizes the week's productivity

### Step 14: Deployment options

| Option | Difficulty | Cost |
|--------|-----------|------|
| **Your own PC** (always-on) | Easy | Free |
| **Raspberry Pi** | Easy | ~$50 one-time |
| **Railway.app** | Easy | Free tier available |
| **A small VPS** (e.g., DigitalOcean, Hetzner) | Medium | ~$4–6/month |
| **Oracle Cloud free tier** | Medium | Free (always-free ARM instance) |

For a personal bot, a Raspberry Pi or cheap VPS is ideal. The bot is lightweight — SQLite + Python uses minimal resources.

**To run as a service on Linux:**

```bash
# Create a systemd service file
sudo nano /etc/systemd/system/productivity-bot.service
```

```ini
[Unit]
Description=Discord Productivity Bot
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/path/to/productivity-bot
ExecStart=/path/to/productivity-bot/venv/bin/python bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

---

## Command Cheat Sheet

| What you type | What happens |
|---------------|-------------|
| `!save https://... #python` | Saves link with tag |
| `!links` | Shows unread links |
| `!todo add Write the report` | Adds today's task |
| `!today` | Shows today's todo list |
| `!todo done 3` | Marks task 3 complete |
| `!goal add Run a marathon` | Adds to bucket list |
| `!goals` | Shows all long-term goals |
| `!log Finished the API refactor, blocked on deployment` | Logs progress |
| `!reflect` | Claude summarizes your day |
| `!remind at 9pm Call Sarah` | Sets timed reminder |
| `!remind before heading_out Grab the package` | Sets context reminder |
| `!heading out` | Shows all "heading out" reminders |
| `!email check` | Shows important unread emails |
| `!mentions` | Shows recent Discord mentions |
| Or just type naturally... | Claude figures out the intent |

---

## Estimated Costs

- **Discord Bot**: Free
- **Anthropic API**: ~$1–5/month for personal use (Haiku is very cheap for command routing)
- **Gmail API**: Free (within quota)
- **Hosting**: Free to $6/month depending on option
- **Total**: Roughly **$1–10/month**

> **Tip**: Use `claude-haiku-4-5-20251001` for command routing (fast, cheap) and
> `claude-sonnet-4-6` for reflections and summaries (smarter, still affordable).
