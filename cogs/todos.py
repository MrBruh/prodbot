from datetime import date

import discord
from discord.ext import commands

from database import get_db


class Todos(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="todo", invoke_without_command=True)
    async def todo(self, ctx):
        """Show today's tasks. Usage: !todo"""
        await self._show_tasks(ctx, str(date.today()))

    @todo.command(name="add")
    async def todo_add(self, ctx, *, task: str):
        """Add a task for today. Usage: !todo add <task>"""
        today = str(date.today())
        async with get_db() as db:
            await db.execute("INSERT INTO todos (date, task) VALUES (?, ?)", (today, task))
            await db.commit()
        await ctx.send(f"Added: **{task}**")

    @todo.command(name="done")
    async def todo_done(self, ctx, task_id: int):
        """Mark a task as complete. Usage: !todo done <id>"""
        async with get_db() as db:
            cursor = await db.execute("UPDATE todos SET completed = 1 WHERE id = ?", (task_id,))
            await db.commit()
            if cursor.rowcount == 0:
                await ctx.send(f"No task found with ID {task_id}.")
                return
        await ctx.send(f"Task #{task_id} marked as done!")

    @todo.command(name="date")
    async def todo_date(self, ctx, target_date: str):
        """View tasks for a specific date. Usage: !todo date 2025-03-20"""
        await self._show_tasks(ctx, target_date)

    @todo.command(name="remove")
    async def todo_remove(self, ctx, task_id: int):
        """Remove a task by ID. Usage: !todo remove <id>"""
        async with get_db() as db:
            db.row_factory = _dict_factory
            cursor = await db.execute("SELECT * FROM todos WHERE id = ?", (task_id,))
            row = await cursor.fetchone()
            if not row:
                await ctx.send(f"No task found with ID #{task_id}.")
                return
            await db.execute("DELETE FROM todos WHERE id = ?", (task_id,))
            await db.commit()
        await ctx.send(f"Removed: **{row['task']}** (#{task_id})")

    @todo.command(name="clear")
    async def todo_clear(self, ctx, target_date: str = None):
        """Remove all tasks for a date. Usage: !todo clear [date]"""
        target_date = target_date or str(date.today())
        async with get_db() as db:
            cursor = await db.execute("DELETE FROM todos WHERE date = ?", (target_date,))
            await db.commit()
            count = cursor.rowcount
        if count == 0:
            await ctx.send(f"No tasks to clear for {target_date}.")
        else:
            await ctx.send(f"Cleared {count} task(s) for {target_date}.")

    @commands.command(name="today")
    async def today(self, ctx):
        """Alias for !todo — show today's tasks."""
        await self._show_tasks(ctx, str(date.today()))

    async def _show_tasks(self, ctx, target_date: str):
        async with get_db() as db:
            db.row_factory = _dict_factory
            cursor = await db.execute(
                "SELECT * FROM todos WHERE date = ? ORDER BY id", (target_date,)
            )
            tasks = await cursor.fetchall()

        if not tasks:
            await ctx.send(f"No tasks for {target_date}.")
            return

        completed = sum(1 for t in tasks if t["completed"])
        total = len(tasks)
        pct = int((completed / total) * 100) if total else 0

        lines = []
        for i, t in enumerate(tasks, 1):
            icon = "done" if t["completed"] else "  "
            lines.append(f"[{icon}] {i}. {t['task']} (#{t['id']})")

        task_list = "\n".join(lines)
        embed = discord.Embed(
            title=f"Tasks ({target_date})",
            description=f"```\n{task_list}\n```",
            color=discord.Color.gold(),
        )
        embed.set_footer(text=f"Progress: {completed}/{total} ({pct}%)")
        await ctx.send(embed=embed)


def _dict_factory(cursor, row):
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


async def setup(bot):
    await bot.add_cog(Todos(bot))
