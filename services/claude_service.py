import json
import re
from datetime import datetime
from typing import Optional

import anthropic

from config import ANTHROPIC_API_KEY


def _strip_code_fences(text: str) -> str:
    """Strip markdown code fences from LLM responses."""
    return re.sub(r"^```(?:json)?\s*\n?|```\s*$", "", text.strip())


client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)


async def summarize_url(url: str) -> str:
    """Ask Claude to generate a short title/summary for a URL."""
    message = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=100,
        messages=[
            {
                "role": "user",
                "content": f"Generate a short title (under 10 words) for this URL: {url}. Reply with just the title, nothing else.",
            }
        ],
    )
    return message.content[0].text


async def reflect_on_day(todos: list, journal_entries: list) -> str:
    """Ask Claude to summarize the user's day."""
    todo_text = "\n".join(f"- [{'x' if t['completed'] else ' '}] {t['task']}" for t in todos)
    journal_text = "\n".join(f"- {e['entry']}" for e in journal_entries)

    prompt = f"""Here's a summary of the user's day:

Tasks:
{todo_text or "No tasks today."}

Journal entries:
{journal_text or "No journal entries."}

You are Jarvis, a productivity assistant. Write a brief, encouraging reflection (2-3 sentences) about their day. Note what they accomplished and gently suggest what they might follow up on tomorrow."""

    message = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


async def parse_reminder_time(text: str) -> dict:
    """Use Claude to parse natural language time expressions into structured data.

    Returns a dict with:
        remind_at: ISO datetime string or None (for timed reminders)
        context: context name or None (for context-based reminders)
        message: the reminder message
    """
    now = datetime.now().isoformat()

    prompt = f"""Parse this reminder request and return JSON only. Current time: {now}

Input: "{text}"

Return a JSON object with exactly these keys:
- "remind_at": ISO datetime string if this is a timed reminder, or null if context-based
- "context": MUST be one of these exact values if context-based: "heading_out", "morning", "evening" — or null if timed. Any mention of heading out, leaving, heading home etc. should map to "heading_out".
- "message": the reminder message text (without the time/context part)

Examples:
- "at 9pm Call Sarah" -> {{"remind_at": "2026-03-15T21:00:00", "context": null, "message": "Call Sarah"}}
- "in 2 hours check email" -> {{"remind_at": "2026-03-15T16:00:00", "context": null, "message": "check email"}}
- "before heading out Bring package" -> {{"remind_at": null, "context": "heading_out", "message": "Bring package"}}
- "before I leave grab keys" -> {{"remind_at": null, "context": "heading_out", "message": "grab keys"}}
- "morning Take vitamins" -> {{"remind_at": null, "context": "morning", "message": "Take vitamins"}}

Reply with ONLY the JSON object, nothing else."""

    message = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    return json.loads(_strip_code_fences(message.content[0].text))


def _tool(
    name: str,
    description: str,
    properties: Optional[dict] = None,
    required: Optional[list] = None,
) -> dict:
    """Build an Anthropic tool definition from its name, description, and schema parts."""
    input_schema: dict = {
        "type": "object",
        "properties": properties or {},
        "additionalProperties": False,
    }
    if required:
        input_schema["required"] = required
    return {"name": name, "description": description, "input_schema": input_schema}


# One tool per routable action. The schemas carry the parameter docs that used to
# live in the system prompt, so the model fills them in directly via tool use.
TOOLS = [
    _tool(
        "add_todo",
        "Add a single task to today's todo list.",
        {"task": {"type": "string", "description": "The task description."}},
        ["task"],
    ),
    _tool(
        "add_todos",
        "Add several tasks to today's todo list at once. Use when the user lists "
        "multiple tasks, e.g. 'add these: 1. Buy groceries 2. Clean house'.",
        {
            "tasks": {
                "type": "array",
                "items": {"type": "string"},
                "description": "The list of task descriptions.",
            }
        },
        ["tasks"],
    ),
    _tool(
        "list_todos",
        "Show the user's todo list for a given day.",
        {
            "date": {
                "type": "string",
                "description": "'today' or an ISO date 'YYYY-MM-DD'. Defaults to today.",
            }
        },
    ),
    _tool(
        "complete_todo",
        "Mark a todo item as done by its numeric ID.",
        {"task_id": {"type": "integer", "description": "The numeric ID of the task."}},
        ["task_id"],
    ),
    _tool(
        "remove_todo",
        "Delete a todo item by its numeric ID.",
        {"task_id": {"type": "integer", "description": "The numeric ID of the task."}},
        ["task_id"],
    ),
    _tool(
        "clear_todos",
        "Remove all todo items for a given day.",
        {
            "date": {
                "type": "string",
                "description": "'today' or an ISO date 'YYYY-MM-DD'. Defaults to today.",
            }
        },
    ),
    _tool(
        "save_link",
        "Save a URL for the user to read later, optionally with tags.",
        {
            "url": {"type": "string", "description": "The URL to save."},
            "tags": {
                "type": "string",
                "description": "Optional space- or comma-separated tags.",
            },
        },
        ["url"],
    ),
    _tool(
        "list_links",
        "List the user's saved links.",
        {
            "filter": {
                "type": "string",
                "enum": ["unread", "read", "all"],
                "description": "Which links to show. Defaults to unread.",
            }
        },
    ),
    _tool(
        "add_goal",
        "Add a long-term goal or bucket-list item.",
        {
            "goal": {"type": "string", "description": "The goal text."},
            "category": {
                "type": "string",
                "description": "Optional category, e.g. 'health'. Defaults to 'general'.",
            },
        },
        ["goal"],
    ),
    _tool("list_goals", "List the user's goals / bucket list."),
    _tool(
        "log_journal",
        "Add a journal entry for today.",
        {"entry": {"type": "string", "description": "The journal entry text."}},
        ["entry"],
    ),
    _tool("reflect", "Reflect on the user's day from their todos and journal entries."),
    _tool(
        "set_reminder",
        "Set a reminder for a specific time or before a context like heading out.",
        {
            "raw_input": {
                "type": "string",
                "description": (
                    "The reminder restated for parsing, beginning with a token: "
                    "'at <time> <message>', 'before <context> <message>', or "
                    "'morning <message>'. Example: 'at 9pm call Sarah'."
                ),
            }
        },
        ["raw_input"],
    ),
    _tool(
        "check_context_reminders",
        "Fire the user's context reminders when they say they are heading out, "
        "leaving, or heading home.",
        {
            "context": {
                "type": "string",
                "enum": ["heading_out"],
                "description": "The context to fire. Only 'heading_out' is supported.",
            }
        },
        ["context"],
    ),
    _tool("list_reminders", "List the user's active reminders."),
    _tool(
        "remove_reminder",
        "Remove a reminder by its numeric ID.",
        {"reminder_id": {"type": "integer", "description": "The numeric ID of the reminder."}},
        ["reminder_id"],
    ),
    _tool("clear_reminders", "Remove all of the user's active reminders."),
    _tool("check_email", "Check the user's email inbox."),
    _tool("check_mentions", "Check the user's mentions."),
    _tool("check_notifications", "Check the user's notifications."),
    _tool(
        "general_chat",
        "Respond conversationally when no other action fits — greetings, small "
        "talk, or general questions. Always include a friendly reply.",
        {
            "response": {
                "type": "string",
                "description": "The conversational reply to send to the user.",
            }
        },
        ["response"],
    ),
]

ROUTING_SYSTEM_PROMPT = (
    "You are Jarvis, a productivity assistant Discord bot. Decide what the user "
    "wants and call exactly one tool. When several tasks are listed at once, use "
    "add_todos. If nothing else fits — greetings, small talk, or general "
    "questions — call general_chat with a friendly reply."
)


async def route_command(user_message: str) -> dict:
    """Determine user intent via native Anthropic tool use and return a structured action.

    Returns ``{"action": <name>, "parameters": {...}}`` for command actions, and
    ``{"action": "general_chat", "parameters": {}, "response": <reply>}`` for chat.
    """
    message = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        system=ROUTING_SYSTEM_PROMPT,
        tools=TOOLS,
        tool_choice={"type": "any", "disable_parallel_tool_use": True},
        messages=[{"role": "user", "content": user_message}],
    )

    tool_block = next(
        (b for b in message.content if getattr(b, "type", None) == "tool_use"),
        None,
    )

    # Defensive fallback: no tool_use block means an API/model failure (e.g.
    # stop_reason == "end_turn"), NOT the old ambiguous-text path. With forced
    # tool use, ambiguous input now deterministically routes to general_chat.
    if tool_block is None:
        text = "".join(
            getattr(b, "text", "") for b in message.content if getattr(b, "type", None) == "text"
        )
        return {
            "action": "general_chat",
            "parameters": {},
            "response": text or "I'm not sure what you mean.",
        }

    params = dict(tool_block.input)

    # general_chat carries its reply in the tool input; lift it to the top level
    # so the return shape matches the original {action, parameters, response}.
    if tool_block.name == "general_chat":
        return {
            "action": "general_chat",
            "parameters": {},
            "response": params.get("response", "I'm not sure what you mean."),
        }

    return {"action": tool_block.name, "parameters": params}
