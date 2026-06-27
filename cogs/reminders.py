import logging
from datetime import datetime
from typing import Optional

import discord
from discord.ext import commands

from config import BOT_CHANNEL_NAME
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
        self.bot.loop.create_task(self._reschedule_reminders())

    async def _reschedule_reminders(self):
        """Reschedule future timed reminders into the in-memory scheduler on startup."""
        await self.bot.wait_until_ready()
        now = datetime.now().isoformat()
        async with get_db() as db:
            db.row_factory = _dict_factory
            # Reschedule future reminders
            cursor = await db.execute(
                "SELECT * FROM reminders WHERE remind_at IS NOT NULL AND remind_at > ? AND fired = 0",
                (now,),
            )
            future = await cursor.fetchall()

            for r in future:
                remind_at = datetime.fromisoformat(r["remind_at"])
                scheduler.add_job(
                    _send_reminder,
                    "date",
                    run_date=remind_at,
                    args=[
                        self.bot,
                        r["channel_id"],
                        r["id"],
                        r["message"],
                        r.get("target_user_id"),
                    ],
                    id=f"reminder_{r['id']}",
                )

            if future:
                logger.info("Rescheduled %d future reminder(s)", len(future))

            # Fire missed reminders (past-due)
            cursor = await db.execute(
                "SELECT * FROM reminders WHERE remind_at IS NOT NULL AND remind_at <= ? AND fired = 0",
                (now,),
            )
            missed = await cursor.fetchall()

            if not missed:
                return

            # Delete them. placeholders is only "?,?,..." bind markers (ids are
            # passed as parameters), so this is not SQL injection.
            ids = [r["id"] for r in missed]
            placeholders = ",".join("?" * len(ids))
            await db.execute(f"DELETE FROM reminders WHERE id IN ({placeholders})", ids)  # noqa: S608
            await db.commit()

        for r in missed:
            channel = self.bot.get_channel(r["channel_id"]) if r.get("channel_id") else None
            if not channel:
                channel = _find_bot_channel(self.bot)
            if not channel:
                logger.warning("Could not find channel to send missed reminder #%s", r["id"])
                continue

            embed = discord.Embed(
                title="Missed Reminder",
                description=f"**{r['message']}**\nWas scheduled for: {r['remind_at']}",
                color=discord.Color.red(),
            )
            ping_id = r.get("target_user_id") or r.get("user_id")
            ping = f"<@{ping_id}>" if ping_id else None
            await channel.send(content=ping, embed=embed)

    async def create_reminder(self, ctx, *, message, remind_at=None, context=None, target=None):
        """Create a timed or context reminder, persist it, schedule it, and confirm.

        Provide exactly one of ``remind_at`` (an ISO 8601 string) or ``context``.
        ``target`` defaults to the command author; pass a member/user to remind
        someone else. Shared by the ``!remind`` commands and the NL router so the
        creation logic (DB insert, scheduler job, target user, embed) lives in one
        place. Returns True if a reminder was created, False otherwise.
        """
        target = target or ctx.author
        message = (message or "").strip()
        if not message:
            await ctx.send("The reminder needs a message. Please try again.")
            return False

        if context:
            async with get_db() as db:
                await db.execute(
                    "INSERT INTO reminders (message, context, user_id, target_user_id, channel_id) VALUES (?, ?, ?, ?, ?)",
                    (message, context, ctx.author.id, target.id, ctx.channel.id),
                )
                await db.commit()
            desc = f"**{message}**\nContext: `{context}`"
        elif remind_at:
            try:
                when = datetime.fromisoformat(remind_at)
            except (TypeError, ValueError):
                await ctx.send("Could not parse the reminder time. Please try again.")
                return False

            async with get_db() as db:
                cursor = await db.execute(
                    "INSERT INTO reminders (message, remind_at, user_id, target_user_id, channel_id) VALUES (?, ?, ?, ?, ?)",
                    (message, remind_at, ctx.author.id, target.id, ctx.channel.id),
                )
                reminder_id = cursor.lastrowid
                await db.commit()

            scheduler.add_job(
                _send_reminder,
                "date",
                run_date=when,
                args=[self.bot, ctx.channel.id, reminder_id, message, target.id],
                id=f"reminder_{reminder_id}",
            )
            desc = f"**{message}**\nTime: {when.strftime('%Y-%m-%d %H:%M')}"
        else:
            await ctx.send("Could not parse the reminder. Please try again.")
            return False

        if target != ctx.author:
            desc += f"\nFor: {target.mention}"
        embed = discord.Embed(title="Reminder Set", description=desc, color=discord.Color.blue())
        await ctx.send(embed=embed)
        return True

    @commands.group(name="remind", invoke_without_command=True)
    async def remind(self, ctx, *, text: str):
        """Set a reminder. Usage: !remind at <time> <message> | !remind before <context> <message> | !remind at <time> @user <message>"""
        # Extract mentioned user as target, fall back to author
        target = ctx.message.mentions[0] if ctx.message.mentions else ctx.author
        # Strip mention from text before parsing
        clean_text = text
        for mention in ctx.message.mentions:
            clean_text = clean_text.replace(f"<@{mention.id}>", "").replace(f"<@!{mention.id}>", "")
        clean_text = clean_text.strip()

        parsed = await parse_reminder_time(clean_text)
        await self.create_reminder(
            ctx,
            message=parsed.get("message", ""),
            remind_at=parsed.get("remind_at"),
            context=parsed.get("context"),
            target=target,
        )

    @remind.command(name="at")
    async def remind_at(self, ctx, *, text: str):
        """Set a timed reminder. Usage: !remind at <time> <message>"""
        await self.remind.callback(self, ctx, text=f"at {text}")

    @remind.command(name="before")
    async def remind_before(self, ctx, context: str, *, message: str):
        """Set a context-based reminder. Usage: !remind before <context> <message> | !remind before <context> @user <message>"""
        target = ctx.message.mentions[0] if ctx.message.mentions else ctx.author
        clean_msg = message
        for mention in ctx.message.mentions:
            clean_msg = clean_msg.replace(f"<@{mention.id}>", "").replace(f"<@!{mention.id}>", "")
        clean_msg = clean_msg.strip()
        await self.create_reminder(ctx, message=clean_msg, context=context, target=target)

    @remind.command(name="morning")
    async def remind_morning(self, ctx, *, message: str):
        """Set a morning context reminder. Usage: !remind morning <message> | !remind morning @user <message>"""
        target = ctx.message.mentions[0] if ctx.message.mentions else ctx.author
        clean_msg = message
        for mention in ctx.message.mentions:
            clean_msg = clean_msg.replace(f"<@{mention.id}>", "").replace(f"<@!{mention.id}>", "")
        clean_msg = clean_msg.strip()
        await self.create_reminder(ctx, message=clean_msg, context="morning", target=target)

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

    @remind.command(name="clear")
    async def remind_clear(self, ctx):
        """Remove all active reminders. Usage: !remind clear"""
        async with get_db() as db:
            cursor = await db.execute("DELETE FROM reminders WHERE fired = 0")
            await db.commit()
            count = cursor.rowcount

        # Cancel all scheduled jobs
        for job in scheduler.get_jobs():
            if job.id.startswith("reminder_"):
                job.remove()

        if count == 0:
            await ctx.send("No active reminders to clear.")
        else:
            embed = discord.Embed(
                title="Reminders Cleared",
                description=f"Removed {count} reminder(s).",
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
        """List active reminders. Usage: !reminders [@user]"""
        mentioned = ctx.message.mentions[0] if ctx.message.mentions else None
        async with get_db() as db:
            db.row_factory = _dict_factory
            if mentioned:
                cursor = await db.execute(
                    "SELECT * FROM reminders WHERE fired = 0 AND (target_user_id = ? OR user_id = ?) ORDER BY id",
                    (mentioned.id, mentioned.id),
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM reminders WHERE fired = 0 ORDER BY id",
                )
            reminders = await cursor.fetchall()

        title_suffix = f" for {mentioned.display_name}" if mentioned else ""
        if not reminders:
            embed = discord.Embed(
                title=f"Reminders{title_suffix}",
                description="No active reminders.",
                color=discord.Color.light_grey(),
            )
            await ctx.send(embed=embed)
            return

        lines = []
        for i, r in enumerate(reminders, 1):
            target = (
                f" → <@{r['target_user_id']}>"
                if r.get("target_user_id") and r["target_user_id"] != r.get("user_id")
                else ""
            )
            if r["remind_at"]:
                lines.append(f"{i}. {r['message']}{target} — {r['remind_at']} (#{r['id']})")
            elif r["context"]:
                lines.append(
                    f"{i}. {r['message']}{target} — context: `{r['context']}` (#{r['id']})"
                )
            else:
                lines.append(f"{i}. {r['message']}{target} (#{r['id']})")

        embed = discord.Embed(
            title=f"Active Reminders{title_suffix}",
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
            ping_id = r.get("target_user_id") or r.get("user_id")
            if ping_id:
                user_ids.add(ping_id)

        pings = " ".join(f"<@{uid}>" for uid in user_ids)
        embed = discord.Embed(
            title=f"Reminders — {context}",
            description="\n".join(lines),
            color=discord.Color.green(),
        )
        embed.set_footer(text=f"{len(reminders)} reminder(s) fired")
        await ctx.send(content=pings or None, embed=embed)


async def _send_reminder(
    bot, channel_id: int, reminder_id: int, message: str, target_user_id: Optional[int] = None
):
    """Callback for APScheduler to send a timed reminder."""
    channel = bot.get_channel(channel_id)
    if channel:
        embed = discord.Embed(
            title="Reminder",
            description=message,
            color=discord.Color.red(),
        )
        ping = f"<@{target_user_id}>" if target_user_id else None
        await channel.send(content=ping, embed=embed)

    async with get_db() as db:
        await db.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        await db.commit()


def _find_bot_channel(bot):
    """Find the first text channel named after BOT_CHANNEL_NAME across all guilds."""
    for guild in bot.guilds:
        for channel in guild.text_channels:
            if channel.name == BOT_CHANNEL_NAME:
                return channel
    return None


def _dict_factory(cursor, row):
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


async def setup(bot):
    await bot.add_cog(Reminders(bot))
