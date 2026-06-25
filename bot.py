import asyncio
import logging

import discord
from discord.ext import commands

from config import BOT_CHANNEL_NAME, DISCORD_TOKEN
from database import init_db
from services.claude_service import route_command

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    await init_db()
    logger.info(f"Logged in as {bot.user}")


# --- Action handlers ---------------------------------------------------------
# Each handler takes (ctx, result) and invokes the matching prefix command.
# `result` is the dict returned by route_command: {action, parameters, response?}.
# Per-action parameter adaptation lives here so on_message stays a plain table
# lookup. Handlers may raise; on_message wraps the call and reports failures.


async def _handle_general_chat(ctx, result):
    await ctx.channel.send(result.get("response") or "I'm not sure what you mean.")


async def _handle_add_todo(ctx, result):
    cmd = ctx.bot.get_command("todo add")
    if cmd:
        await ctx.invoke(cmd, task=result["parameters"].get("task", ""))


async def _handle_add_todos(ctx, result):
    cmd = ctx.bot.get_command("todo add")
    if cmd:
        for task in result["parameters"].get("tasks", []):
            await ctx.invoke(cmd, task=task)


async def _handle_clear_todos(ctx, result):
    cmd = ctx.bot.get_command("todo clear")
    if cmd:
        date_param = result["parameters"].get("date", "today")
        await ctx.invoke(cmd, target_date=date_param if date_param != "today" else None)


async def _handle_list_todos(ctx, result):
    date_param = result["parameters"].get("date", "today")
    if date_param == "today":
        cmd = ctx.bot.get_command("today")
        if cmd:
            await ctx.invoke(cmd)
    else:
        cmd = ctx.bot.get_command("todo date")
        if cmd:
            await ctx.invoke(cmd, target_date=date_param)


async def _handle_complete_todo(ctx, result):
    cmd = ctx.bot.get_command("todo done")
    if cmd:
        await ctx.invoke(cmd, task_id=result["parameters"].get("task_id"))


async def _handle_remove_todo(ctx, result):
    cmd = ctx.bot.get_command("todo remove")
    if cmd:
        await ctx.invoke(cmd, task_id=result["parameters"].get("task_id"))


async def _handle_save_link(ctx, result):
    cmd = ctx.bot.get_command("save")
    if cmd:
        params = result["parameters"]
        await ctx.invoke(cmd, url=params.get("url", ""), tags=params.get("tags", ""))


async def _handle_list_links(ctx, result):
    cmd = ctx.bot.get_command("links")
    if cmd:
        await ctx.invoke(cmd, filter=result["parameters"].get("filter", "unread"))


async def _handle_add_goal(ctx, result):
    cmd = ctx.bot.get_command("goal add")
    if cmd:
        # goal add takes (*, text: str) — format as "goal #category"
        params = result["parameters"]
        goal = params.get("goal", "")
        category = params.get("category", "general")
        text = f"{goal} #{category}" if category != "general" else goal
        await ctx.invoke(cmd, text=text)


async def _handle_list_goals(ctx, result):
    cmd = ctx.bot.get_command("goals")
    if cmd:
        await ctx.invoke(cmd)


async def _handle_log_journal(ctx, result):
    cmd = ctx.bot.get_command("log")
    if cmd:
        await ctx.invoke(cmd, entry=result["parameters"].get("entry", ""))


async def _handle_reflect(ctx, result):
    cmd = ctx.bot.get_command("reflect")
    if cmd:
        await ctx.invoke(cmd)


async def _handle_set_reminder(ctx, result):
    # Phase 2a: keep emitting a raw_input-style string and the existing split.
    # Known brittleness: a raw_input without a leading at/before/morning token
    # falls through to the remind group, which may silently do nothing.
    raw = result["parameters"].get("raw_input", "")
    parts = raw.split(None, 1)
    if len(parts) < 2:
        return
    sub, rest = parts[0], parts[1]
    subcmd = ctx.bot.get_command(f"remind {sub}")
    if subcmd:
        if sub == "before":
            # remind before takes (context, *, message)
            before_parts = rest.split(None, 1)
            if len(before_parts) >= 2:
                await ctx.invoke(subcmd, context=before_parts[0], message=before_parts[1])
        elif sub == "at":
            await ctx.invoke(subcmd, text=rest)
        elif sub == "morning":
            await ctx.invoke(subcmd, message=rest)
    else:
        # Fallback: pass raw text to the remind group
        cmd = ctx.bot.get_command("remind")
        if cmd:
            await ctx.invoke(cmd, text=raw)


async def _handle_check_context_reminders(ctx, result):
    # The schema restricts context to heading_out; only that path is wired.
    context = result["parameters"].get("context", "heading_out")
    if context == "heading_out":
        cmd = ctx.bot.get_command("heading")
        if cmd:
            await ctx.invoke(cmd)


async def _handle_check_email(ctx, result):
    cmd = ctx.bot.get_command("email check")
    if cmd:
        await ctx.invoke(cmd)


async def _handle_check_mentions(ctx, result):
    cmd = ctx.bot.get_command("mentions")
    if cmd:
        await ctx.invoke(cmd)


async def _handle_check_notifications(ctx, result):
    cmd = ctx.bot.get_command("notifications")
    if cmd:
        await ctx.invoke(cmd)


async def _handle_list_reminders(ctx, result):
    cmd = ctx.bot.get_command("reminders")
    if cmd:
        await ctx.invoke(cmd)


async def _handle_remove_reminder(ctx, result):
    cmd = ctx.bot.get_command("remind remove")
    if cmd:
        await ctx.invoke(cmd, reminder_id=result["parameters"].get("reminder_id"))


async def _handle_clear_reminders(ctx, result):
    cmd = ctx.bot.get_command("remind clear")
    if cmd:
        await ctx.invoke(cmd)


DISPATCH = {
    "general_chat": _handle_general_chat,
    "add_todo": _handle_add_todo,
    "add_todos": _handle_add_todos,
    "clear_todos": _handle_clear_todos,
    "list_todos": _handle_list_todos,
    "complete_todo": _handle_complete_todo,
    "remove_todo": _handle_remove_todo,
    "save_link": _handle_save_link,
    "list_links": _handle_list_links,
    "add_goal": _handle_add_goal,
    "list_goals": _handle_list_goals,
    "log_journal": _handle_log_journal,
    "reflect": _handle_reflect,
    "set_reminder": _handle_set_reminder,
    "check_context_reminders": _handle_check_context_reminders,
    "check_email": _handle_check_email,
    "check_mentions": _handle_check_mentions,
    "check_notifications": _handle_check_notifications,
    "list_reminders": _handle_list_reminders,
    "remove_reminder": _handle_remove_reminder,
    "clear_reminders": _handle_clear_reminders,
}


@bot.event
async def on_message(message):
    # Always process prefix commands first
    await bot.process_commands(message)

    # Skip if: bot message, has command prefix, wrong channel
    if message.author.bot:
        return
    if message.content.startswith("!"):
        return
    if getattr(message.channel, "name", None) != BOT_CHANNEL_NAME:
        return

    try:
        result = await route_command(message.content)
    except Exception:
        logger.exception("Failed to route message")
        return

    action = result.get("action", "general_chat")
    ctx = await bot.get_context(message)
    handler = DISPATCH.get(action, _handle_general_chat)

    try:
        await handler(ctx, result)
    except Exception:
        logger.exception("Failed to handle action %r", action)
        await message.channel.send("Sorry, something went wrong handling that.")


async def main():
    async with bot:
        await bot.load_extension("cogs.help")
        await bot.load_extension("cogs.links")
        await bot.load_extension("cogs.todos")
        await bot.load_extension("cogs.bucket_list")
        await bot.load_extension("cogs.journal")
        await bot.load_extension("cogs.reminders")
        await bot.load_extension("cogs.notifications")
        await bot.start(DISCORD_TOKEN)


asyncio.run(main())
