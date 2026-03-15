import anthropic

from config import ANTHROPIC_API_KEY

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

Write a brief, encouraging reflection (2-3 sentences) about their day. Note what they accomplished and gently suggest what they might follow up on tomorrow."""

    message = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text
