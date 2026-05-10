import json
import re
from datetime import datetime

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


async def route_command(user_message: str) -> dict:
    """Use Claude to determine user intent from natural language and return structured action."""
    system_prompt = """You are Jarvis, a productivity assistant Discord bot. Given the user's message, determine what action to take. Respond with JSON only, no other text.

{
  "action": "<action_name>",
  "parameters": { ... },
  "response": "<friendly response if action is general_chat>"
}

Available actions:
- add_todo: parameters: {"task": "..."} (single task)
- add_todos: parameters: {"tasks": ["task1", "task2", ...]} (multiple tasks)
- list_todos: parameters: {"date": "today" or "YYYY-MM-DD"}
- complete_todo: parameters: {"task_id": <int>}
- remove_todo: parameters: {"task_id": <int>}
- clear_todos: parameters: {"date": "today" or "YYYY-MM-DD"}
- save_link: parameters: {"url": "...", "tags": "..."}
- list_links: parameters: {"filter": "unread|read|all"}
- add_goal: parameters: {"goal": "...", "category": "general"}
- list_goals: parameters: {}
- log_journal: parameters: {"entry": "..."}
- reflect: parameters: {}
- set_reminder: parameters: {"raw_input": "the full reminder text for further parsing"}
- check_context_reminders: parameters: {"context": "heading_out|morning|evening"}
- list_reminders: parameters: {}
- remove_reminder: parameters: {"reminder_id": <int>}
- clear_reminders: parameters: {}
- check_email: parameters: {}
- check_mentions: parameters: {}
- check_notifications: parameters: {}
- general_chat: parameters: {}, response: "your conversational reply"

Examples:
- "remind me at 9pm to call Sarah" → {"action": "set_reminder", "parameters": {"raw_input": "at 9pm call Sarah"}}
- "I'm heading out now" → {"action": "check_context_reminders", "parameters": {"context": "heading_out"}}
- "what do I need to do today?" → {"action": "list_todos", "parameters": {"date": "today"}}
- "save this link https://example.com" → {"action": "save_link", "parameters": {"url": "https://example.com", "tags": ""}}
- "how's my day going?" → {"action": "reflect", "parameters": {}}
- "any new emails?" → {"action": "check_email", "parameters": {}}
- "hello!" → {"action": "general_chat", "parameters": {}, "response": "Hey there! How can I help you today?"}
- "add these tasks: 1. Buy groceries 2. Clean house" → {"action": "add_todos", "parameters": {"tasks": ["Buy groceries", "Clean house"]}}
- "remove all todos for today" → {"action": "clear_todos", "parameters": {"date": "today"}}
- "remove all reminders" → {"action": "clear_reminders", "parameters": {}}"""

    message = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    try:
        return json.loads(_strip_code_fences(message.content[0].text))
    except json.JSONDecodeError:
        return {
            "action": "general_chat",
            "parameters": {},
            "response": message.content[0].text,
        }
