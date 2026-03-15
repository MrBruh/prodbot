import asyncio

import discord
from discord.ext import commands

from config import DISCORD_TOKEN
from database import init_db

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    await init_db()
    print(f"Logged in as {bot.user}")


async def main():
    async with bot:
        await bot.load_extension("cogs.links")
        await bot.load_extension("cogs.todos")
        await bot.load_extension("cogs.bucket_list")
        await bot.load_extension("cogs.journal")
        await bot.load_extension("cogs.reminders")
        await bot.load_extension("cogs.notifications")
        await bot.start(DISCORD_TOKEN)


asyncio.run(main())
