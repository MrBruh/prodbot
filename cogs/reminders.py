import logging
from datetime import datetime

import discord
from discord.ext import commands

from config import BOT_CHANNEL_ID
from database import get_db
from services.claude_service import parse_reminder_time
from services.scheduler_service import scheduler, start_scheduler

logger = logging.getLogger(__name__)


class Reminders(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        start_scheduler()

    async def cog_load(self):
        """Check for missed timed reminders on startup."""
        self.bot.loop.create_task(self._fire_missed_reminders())

    async def _fire_missed_reminders(self):
        """Send and delete any timed reminders that were missed while offline."""
        await self.bot.wait_until_ready()
        now = datetime.now().isoformat()
        async with get_db() as db:
            db.row_factory = _dict_factory
            cursor = await db.execute(
                "SELECT * FROM reminders WHERE remind_at IS NOT NULL AND remind_at <= ? AND fired = 0",
                (now,),
            )
            missed = await cursor.fetchall()

            if not missed:
                return

            # Delete them
            ids = [r["id"] for r in missed]
            placeholders = ",".join("?" * len(ids))
            await db.execute(f"DELETE FROM reminders WHERE id IN ({placeholders})", ids)
            await db.commit()

        channel = self.bot.get_channel(BOT_CHANNEL_ID)
        if not channel:
            logger.warning("Could not find bot channel to send missed reminders")
            return

        for r in missed:
            embed = discord.Embed(
                title="Missed Reminder",
                description=f"**{r['message']}**\nWas scheduled for: {r['remind_at']}",
                color=discord.Color.red(),
            )
            ping = f"<@{r['user_id']}>" if r.get("user_id") else None
            await channel.send(content=ping, embed=embed)

    @commands.group(name="remind", invoke_without_command=True)
    async def remind(self, ctx, *, text: str):
        """Set a reminder. Usage: !remind at <time> <message> | !remind before <context> <message>"""
        parsed = await parse_reminder_time(text)

        if parsed.get("context"):
            # Context-based reminder
            async with get_db() as db:
                await db.execute(
                    "INSERT INTO reminders (message, context, user_id) VALUES (?, ?, ?)",
                    (parsed["message"], parsed["context"], ctx.author.id),
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
                    "INSERT INTO reminders (message, remind_at, user_id) VALUES (?, ?, ?)",
                    (parsed["message"], parsed["remind_at"], ctx.author.id),
                )
                reminder_id = cursor.lastrowid
                await db.commit()

            channel_id = ctx.channel.id
            scheduler.add_job(
                _send_reminder,
                "date",
                run_date=remind_at,
                args=[self.bot, channel_id, reminder_id, parsed["message"], ctx.author.id],
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
                "INSERT INTO reminders (message, context, user_id) VALUES (?, ?, ?)",
                (message, context, ctx.author.id),
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
                "INSERT INTO reminders (message, context, user_id) VALUES (?, ?, ?)",
                (message, "morning", ctx.author.id),
            )
            await db.commit()

        embed = discord.Embed(
            title="Reminder Set",
            description=f"**{message}**\nContext: `morning`",
            color=discord.Color.blue(),
        )
        await ctx.send(embed=embed)

    @remind.command(name="remove")
    async def remind_remove(self, ctx, reminder_id: int):
        """Remove a reminder by ID. Usage: !remind remove <id>"""
        async with get_db() as db:
            db.row_factory = _dict_factory
            cursor = await db.execute(
                "SELECT * FROM reminders WHERE id = ? AND fired = 0",
                (reminder_id,),
            )
            row = await cursor.fetchone()
            if not row:
                await ctx.send(f"No active reminder found with ID #{reminder_id}.")
                return

            await db.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
            await db.commit()

            # Remove scheduled job if it exists
            job_id = f"reminder_{reminder_id}"
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)

        details = f"**{row['message']}**"
        if row.get("remind_at"):
            details += f"\nTime: {row['remind_at']}"
        elif row.get("context"):
            details += f"\nContext: `{row['context']}`"

        embed = discord.Embed(
            title="Reminder Removed",
            description=details,
            color=discord.Color.orange(),
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

            # Delete fired reminders
            await db.execute(
                "DELETE FROM reminders WHERE context = ? AND fired = 0",
                (context,),
            )
            await db.commit()

        lines = []
        user_ids = set()
        for i, r in enumerate(reminders, 1):
            lines.append(f"{i}. {r['message']}")
            if r.get("user_id"):
                user_ids.add(r["user_id"])

        pings = " ".join(f"<@{uid}>" for uid in user_ids)
        embed = discord.Embed(
            title=f"Reminders — {context}",
            description="\n".join(lines),
            color=discord.Color.green(),
        )
        embed.set_footer(text=f"{len(reminders)} reminder(s) fired")
        await ctx.send(content=pings or None, embed=embed)


async def _send_reminder(bot, channel_id: int, reminder_id: int, message: str, user_id: int = None):
    """Callback for APScheduler to send a timed reminder."""
    channel = bot.get_channel(channel_id)
    if channel:
        embed = discord.Embed(
            title="Reminder",
            description=message,
            color=discord.Color.red(),
        )
        ping = f"<@{user_id}>" if user_id else None
        await channel.send(content=ping, embed=embed)

    async with get_db() as db:
        await db.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        await db.commit()


def _dict_factory(cursor, row):
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


async def setup(bot):
    await bot.add_cog(Reminders(bot))
