from datetime import date
from typing import Optional

import discord
from discord.ext import commands

from database import get_db
from services.claude_service import reflect_on_day


class Journal(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="log")
    async def log_entry(self, ctx, *, entry: str):
        """Log a progress entry for today. Usage: !log <entry>"""
        today = str(date.today())
        async with get_db() as db:
            await db.execute("INSERT INTO journal (date, entry) VALUES (?, ?)", (today, entry))
            await db.commit()
        await ctx.send("Logged for today.")

    @commands.command(name="journal")
    async def view_journal(self, ctx, target_date: Optional[str] = None):
        """View journal entries for a date. Usage: !journal [date]"""
        target_date = target_date or str(date.today())

        async with get_db() as db:
            db.row_factory = _dict_factory
            cursor = await db.execute(
                "SELECT * FROM journal WHERE date = ? ORDER BY created_at",
                (target_date,),
            )
            entries = await cursor.fetchall()

        if not entries:
            await ctx.send(f"No journal entries for {target_date}.")
            return

        embed = discord.Embed(title=f"Journal — {target_date}", color=discord.Color.teal())
        for e in entries:
            time_str = e["created_at"].split(" ")[-1][:5] if " " in (e["created_at"] or "") else ""
            embed.add_field(
                name=time_str or "Entry",
                value=e["entry"],
                inline=False,
            )
        await ctx.send(embed=embed)

    @commands.command(name="reflect")
    async def reflect(self, ctx):
        """Claude summarizes your day based on todos and journal entries."""
        today = str(date.today())

        async with get_db() as db:
            db.row_factory = _dict_factory
            cursor = await db.execute("SELECT task, completed FROM todos WHERE date = ?", (today,))
            todos = await cursor.fetchall()

            cursor = await db.execute("SELECT entry FROM journal WHERE date = ?", (today,))
            entries = await cursor.fetchall()

        if not todos and not entries:
            await ctx.send("Nothing to reflect on yet — add some tasks or journal entries first.")
            return

        async with ctx.typing():
            reflection = await reflect_on_day(todos, entries)

        embed = discord.Embed(
            title=f"Daily Reflection — {today}",
            description=reflection,
            color=discord.Color.orange(),
        )
        await ctx.send(embed=embed)


def _dict_factory(cursor, row):
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


async def setup(bot):
    await bot.add_cog(Journal(bot))
