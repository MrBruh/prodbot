import logging

import anthropic
import discord
from discord.ext import commands

from database import get_db
from services.claude_service import summarize_url

logger = logging.getLogger(__name__)


class Links(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="save")
    async def save_link(self, ctx, url: str, *, tags: str = ""):
        """Save a link with optional tags. Usage: !save <url> [tags]"""
        try:
            title = await summarize_url(url)
        except anthropic.APIError as e:
            logger.warning(f"Failed to summarize URL: {e}")
            title = None

        async with get_db() as db:
            await db.execute(
                "INSERT INTO links (url, title, tags) VALUES (?, ?, ?)",
                (url, title, tags),
            )
            await db.commit()

        embed = discord.Embed(title="Link Saved", color=discord.Color.green())
        embed.add_field(name="URL", value=url, inline=False)
        if title:
            embed.add_field(name="Title", value=title, inline=False)
        if tags:
            embed.add_field(name="Tags", value=tags, inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="links")
    async def list_links(self, ctx, filter: str = "unread"):
        """Show links. Usage: !links [unread|read|all]"""
        async with get_db() as db:
            db.row_factory = _dict_factory
            if filter == "read":
                cursor = await db.execute(
                    "SELECT * FROM links WHERE read = 1 ORDER BY saved_at DESC"
                )
            elif filter == "all":
                cursor = await db.execute("SELECT * FROM links ORDER BY saved_at DESC")
            else:
                cursor = await db.execute(
                    "SELECT * FROM links WHERE read = 0 ORDER BY saved_at DESC"
                )
            links = await cursor.fetchall()

        if not links:
            await ctx.send(f"No {filter} links found.")
            return

        embed = discord.Embed(
            title=f"Links ({filter})",
            color=discord.Color.blue(),
        )
        for i, link in enumerate(links[:15], 1):
            name = f"{i}. {link['title'] or 'Untitled'} (#{link['id']})"
            value = link["url"]
            if link["tags"]:
                value += f"\nTags: {link['tags']}"
            embed.add_field(name=name, value=value, inline=False)

        await ctx.send(embed=embed)

    @commands.command(name="read")
    async def mark_read(self, ctx, link_id: int):
        """Mark a link as read. Usage: !read <id>"""
        async with get_db() as db:
            cursor = await db.execute("UPDATE links SET read = 1 WHERE id = ?", (link_id,))
            await db.commit()
            if cursor.rowcount == 0:
                await ctx.send(f"No link found with ID {link_id}.")
                return

        await ctx.send(f"Link #{link_id} marked as read.")


def _dict_factory(cursor, row):
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


async def setup(bot):
    await bot.add_cog(Links(bot))
