import asyncio
import logging

import discord
from discord.ext import commands

from config import BOT_CHANNEL_ID, DISCORD_TOKEN
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


@bot.event
async def on_message(message):
    # Always process prefix commands first
    await bot.process_commands(message)

    # Skip if: bot message, has command prefix, wrong channel
    if message.author.bot:
        return
    if message.content.startswith("!"):
        return
    if message.channel.id != BOT_CHANNEL_ID:
        return

    try:
        result = await route_command(message.content)
    except Exception:
        logger.exception("Failed to route message")
        return

    action = result.get("action", "general_chat")
    params = result.get("parameters", {})
    response_text = result.get("response", "I'm not sure what you mean.")

    # Create a context for invoking commands
    ctx = await bot.get_context(message)

    if action == "general_chat":
        await message.channel.send(response_text)
    elif action == "add_todo":
        cmd = bot.get_command("todo add")
        if cmd:
            await ctx.invoke(cmd, task=params.get("task", ""))
    elif action == "add_todos":
        cmd = bot.get_command("todo add")
        if cmd:
            for task in params.get("tasks", []):
                await ctx.invoke(cmd, task=task)
    elif action == "clear_todos":
        cmd = bot.get_command("todo clear")
        if cmd:
            date_param = params.get("date", "today")
            await ctx.invoke(cmd, target_date=date_param if date_param != "today" else None)
    elif action == "list_todos":
        date_param = params.get("date", "today")
        if date_param == "today":
            cmd = bot.get_command("today")
            if cmd:
                await ctx.invoke(cmd)
        else:
            cmd = bot.get_command("todo date")
            if cmd:
                await ctx.invoke(cmd, target_date=date_param)
    elif action == "complete_todo":
        cmd = bot.get_command("todo done")
        if cmd:
            await ctx.invoke(cmd, task_id=params.get("task_id"))
    elif action == "save_link":
        cmd = bot.get_command("save")
        if cmd:
            await ctx.invoke(cmd, url=params.get("url", ""), tags=params.get("tags", ""))
    elif action == "list_links":
        cmd = bot.get_command("links")
        if cmd:
            await ctx.invoke(cmd, filter=params.get("filter", "unread"))
    elif action == "add_goal":
        cmd = bot.get_command("goal add")
        if cmd:
            # goal add takes *, text: str — format as "goal #category"
            goal = params.get("goal", "")
            category = params.get("category", "general")
            text = f"{goal} #{category}" if category != "general" else goal
            await ctx.invoke(cmd, text=text)
    elif action == "list_goals":
        cmd = bot.get_command("goals")
        if cmd:
            await ctx.invoke(cmd)
    elif action == "log_journal":
        cmd = bot.get_command("log")
        if cmd:
            await ctx.invoke(cmd, entry=params.get("entry", ""))
    elif action == "reflect":
        cmd = bot.get_command("reflect")
        if cmd:
            await ctx.invoke(cmd)
    elif action == "set_reminder":
        raw = params.get("raw_input", "")
        parts = raw.split(None, 1)
        if len(parts) >= 2:
            sub = parts[0]
            rest = parts[1]
            subcmd = bot.get_command(f"remind {sub}")
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
                cmd = bot.get_command("remind")
                if cmd:
                    await ctx.invoke(cmd, text=raw)
    elif action == "check_context_reminders":
        context = params.get("context", "heading_out")
        if context == "heading_out":
            cmd = bot.get_command("heading")
            if cmd:
                await ctx.invoke(cmd)
    elif action == "check_email":
        cmd = bot.get_command("email check")
        if cmd:
            await ctx.invoke(cmd)
    elif action == "check_mentions":
        cmd = bot.get_command("mentions")
        if cmd:
            await ctx.invoke(cmd)
    elif action == "check_notifications":
        cmd = bot.get_command("notifications")
        if cmd:
            await ctx.invoke(cmd)
    elif action == "list_reminders":
        cmd = bot.get_command("reminders")
        if cmd:
            await ctx.invoke(cmd)
    elif action == "remove_reminder":
        cmd = bot.get_command("remind remove")
        if cmd:
            await ctx.invoke(cmd, reminder_id=params.get("reminder_id"))
    elif action == "clear_reminders":
        cmd = bot.get_command("remind clear")
        if cmd:
            await ctx.invoke(cmd)
    else:
        await message.channel.send(response_text)


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
