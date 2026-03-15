from datetime import datetime

import discord
from discord.ext import commands

from database import get_db
from services.claude_service import parse_reminder_time
from services.scheduler_service import scheduler, start_scheduler


class Reminders(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        start_scheduler()

    @commands.group(name="remind", invoke_without_command=True)
    async def remind(self, ctx, *, text: str):
        """Set a reminder. Usage: !remind at <time> <message> | !remind before <context> <message>"""
        parsed = await parse_reminder_time(text)

        if parsed.get("context"):
            # Context-based reminder
            async with get_db() as db:
                await db.execute(
                    "INSERT INTO reminders (message, context) VALUES (?, ?)",
                    (parsed["message"], parsed["context"]),
                )
                await db.commit()

            embed = discord.Embed(
                title="Reminder Set",
                description=f"**{parsed['message']}**\nContext: `{parsed['context']}`",
                color=discord.Color.blue(),
            )
            await ctx.send(embed=embed)

        elif parsed.get("remind_at"):
            # Timed reminder
            remind_at = datetime.fromisoformat(parsed["remind_at"])

            async with get_db() as db:
                cursor = await db.execute(
                    "INSERT INTO reminders (message, remind_at) VALUES (?, ?)",
                    (parsed["message"], parsed["remind_at"]),
                )
                reminder_id = cursor.lastrowid
                await db.commit()

            channel_id = ctx.channel.id
            scheduler.add_job(
                _send_reminder,
                "date",
                run_date=remind_at,
                args=[self.bot, channel_id, reminder_id, parsed["message"]],
                id=f"reminder_{reminder_id}",
            )

            embed = discord.Embed(
                title="Reminder Set",
                description=f"**{parsed['message']}**\nTime: {remind_at.strftime('%Y-%m-%d %H:%M')}",
                color=discord.Color.blue(),
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send("Could not parse the reminder. Please try again.")

    @remind.command(name="at")
    async def remind_at(self, ctx, *, text: str):
        """Set a timed reminder. Usage: !remind at <time> <message>"""
        await self.remind.callback(self, ctx, text=f"at {text}")

    @remind.command(name="before")
    async def remind_before(self, ctx, context: str, *, message: str):
        """Set a context-based reminder. Usage: !remind before <context> <message>"""
        async with get_db() as db:
            await db.execute(
                "INSERT INTO reminders (message, context) VALUES (?, ?)",
                (message, context),
            )
            await db.commit()

        embed = discord.Embed(
            title="Reminder Set",
            description=f"**{message}**\nContext: `{context}`",
            color=discord.Color.blue(),
        )
        await ctx.send(embed=embed)

    @remind.command(name="morning")
    async def remind_morning(self, ctx, *, message: str):
        """Set a morning context reminder. Usage: !remind morning <message>"""
        async with get_db() as db:
            await db.execute(
                "INSERT INTO reminders (message, context) VALUES (?, ?)",
                (message, "morning"),
            )
            await db.commit()

        embed = discord.Embed(
            title="Reminder Set",
            description=f"**{message}**\nContext: `morning`",
            color=discord.Color.blue(),
        )
        await ctx.send(embed=embed)

    @commands.command(name="heading")
    async def heading_out(self, ctx, *, _rest: str = "out"):
        """Trigger heading_out reminders. Usage: !heading out"""
        await self._fire_context_reminders(ctx, "heading_out")

    @commands.command(name="leaving")
    async def leaving(self, ctx):
        """Trigger heading_out reminders. Usage: !leaving"""
        await self._fire_context_reminders(ctx, "heading_out")

    @commands.command(name="reminders")
    async def list_reminders(self, ctx):
        """List all active (unfired) reminders. Usage: !reminders"""
        async with get_db() as db:
            db.row_factory = _dict_factory
            cursor = await db.execute(
                "SELECT * FROM reminders WHERE fired = 0 ORDER BY id",
            )
            reminders = await cursor.fetchall()

        if not reminders:
            embed = discord.Embed(
                title="Reminders",
                description="No active reminders.",
                color=discord.Color.light_grey(),
            )
            await ctx.send(embed=embed)
            return

        lines = []
        for i, r in enumerate(reminders, 1):
            if r["remind_at"]:
                lines.append(f"{i}. {r['message']} — {r['remind_at']} (#{r['id']})")
            elif r["context"]:
                lines.append(f"{i}. {r['message']} — context: `{r['context']}` (#{r['id']})")
            else:
                lines.append(f"{i}. {r['message']} (#{r['id']})")

        embed = discord.Embed(
            title="Active Reminders",
            description="\n".join(lines),
            color=discord.Color.blue(),
        )
        embed.set_footer(text=f"{len(reminders)} active reminder(s)")
        await ctx.send(embed=embed)

    async def _fire_context_reminders(self, ctx, context: str):
        """Query and fire all unfired reminders for a given context."""
        async with get_db() as db:
            db.row_factory = _dict_factory
            cursor = await db.execute(
                "SELECT * FROM reminders WHERE context = ? AND fired = 0 ORDER BY id",
                (context,),
            )
            reminders = await cursor.fetchall()

            if not reminders:
                embed = discord.Embed(
                    title=f"No {context} reminders",
                    description=f"No pending reminders for `{context}`.",
                    color=discord.Color.light_grey(),
                )
                await ctx.send(embed=embed)
                return

            # Mark all as fired
            await db.execute(
                "UPDATE reminders SET fired = 1 WHERE context = ? AND fired = 0",
                (context,),
            )
            await db.commit()

        lines = []
        for i, r in enumerate(reminders, 1):
            lines.append(f"{i}. {r['message']}")

        embed = discord.Embed(
            title=f"Reminders — {context}",
            description="\n".join(lines),
            color=discord.Color.green(),
        )
        embed.set_footer(text=f"{len(reminders)} reminder(s) fired")
        await ctx.send(embed=embed)


async def _send_reminder(bot, channel_id: int, reminder_id: int, message: str):
    """Callback for APScheduler to send a timed reminder."""
    channel = bot.get_channel(channel_id)
    if channel:
        embed = discord.Embed(
            title="Reminder",
            description=message,
            color=discord.Color.red(),
        )
        await channel.send(embed=embed)

    async with get_db() as db:
        await db.execute("UPDATE reminders SET fired = 1 WHERE id = ?", (reminder_id,))
        await db.commit()


def _dict_factory(cursor, row):
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


async def setup(bot):
    await bot.add_cog(Reminders(bot))
