import discord
from discord.ext import commands
from database import get_db
from datetime import datetime


class BucketList(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="goal", invoke_without_command=True)
    async def goal(self, ctx):
        """Show all goals. Usage: !goal"""
        await self._show_goals(ctx)

    @goal.command(name="add")
    async def goal_add(self, ctx, *, text: str):
        """Add a long-term goal. Usage: !goal add <goal> [#category]"""
        # Parse category from hashtag if present
        parts = text.rsplit("#", 1)
        goal_text = parts[0].strip()
        category = parts[1].strip() if len(parts) > 1 else "general"

        async with get_db() as db:
            await db.execute(
                "INSERT INTO bucket_list (goal, category) VALUES (?, ?)",
                (goal_text, category),
            )
            await db.commit()
        await ctx.send(f"Goal added: **{goal_text}** [{category}]")

    @goal.command(name="progress")
    async def goal_progress(self, ctx, goal_id: int):
        """Mark a goal as in-progress. Usage: !goal progress <id>"""
        async with get_db() as db:
            cursor = await db.execute(
                "UPDATE bucket_list SET status = 'in_progress' WHERE id = ?",
                (goal_id,),
            )
            await db.commit()
            if cursor.rowcount == 0:
                await ctx.send(f"No goal found with ID {goal_id}.")
                return
        await ctx.send(f"Goal #{goal_id} marked as in-progress.")

    @goal.command(name="done")
    async def goal_done(self, ctx, goal_id: int):
        """Mark a goal as complete. Usage: !goal done <id>"""
        async with get_db() as db:
            cursor = await db.execute(
                "UPDATE bucket_list SET status = 'done', completed_at = ? WHERE id = ?",
                (datetime.now().isoformat(), goal_id),
            )
            await db.commit()
            if cursor.rowcount == 0:
                await ctx.send(f"No goal found with ID {goal_id}.")
                return
        await ctx.send(f"Goal #{goal_id} completed!")

    @commands.command(name="goals")
    async def goals(self, ctx):
        """Alias for !goal — show all goals."""
        await self._show_goals(ctx)

    async def _show_goals(self, ctx):
        async with get_db() as db:
            db.row_factory = _dict_factory
            cursor = await db.execute(
                "SELECT * FROM bucket_list ORDER BY category, status, id"
            )
            goals = await cursor.fetchall()

        if not goals:
            await ctx.send("No goals yet. Add one with `!goal add <goal> #category`")
            return

        # Group by category
        categories = {}
        for g in goals:
            cat = g["category"]
            categories.setdefault(cat, []).append(g)

        embed = discord.Embed(title="Bucket List", color=discord.Color.purple())
        status_icons = {
            "not_started": "[ ]",
            "in_progress": "[~]",
            "done": "[x]",
        }
        for cat, items in categories.items():
            lines = []
            for g in items:
                icon = status_icons.get(g["status"], "[ ]")
                lines.append(f"{icon} #{g['id']} {g['goal']}")
            embed.add_field(name=cat.title(), value="\n".join(lines), inline=False)

        await ctx.send(embed=embed)


def _dict_factory(cursor, row):
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


async def setup(bot):
    await bot.add_cog(BucketList(bot))
