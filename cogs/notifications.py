import logging
from typing import Dict, List

import discord
from discord.ext import commands

from services.gmail_service import get_unread_emails

logger = logging.getLogger(__name__)


class Notifications(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _get_recent_mentions(self, ctx) -> List[Dict]:
        """Scan guild text channels for recent mentions of the invoking user."""
        mentions_found = []
        for channel in ctx.guild.text_channels:
            try:
                async for message in channel.history(limit=50):
                    if ctx.author in message.mentions and message.author != ctx.author:
                        mentions_found.append(
                            {
                                "channel": channel.name,
                                "author": str(message.author),
                                "content": message.content[:100],
                                "created_at": message.created_at.strftime("%Y-%m-%d %H:%M"),
                            }
                        )
            except discord.Forbidden:
                continue
        return mentions_found

    @commands.group(name="email", invoke_without_command=True)
    async def email(self, ctx):
        """Email commands. Usage: !email check"""
        await ctx.send("Usage: `!email check`")

    @email.command(name="check")
    async def email_check(self, ctx):
        """Show unread emails. Usage: !email check"""
        async with ctx.typing():
            emails = await get_unread_emails()

        if emails is None:
            await ctx.send("Gmail is not configured. Add credentials.json to enable email checks.")
            return

        if not emails:
            await ctx.send("No unread emails!")
            return

        embed = discord.Embed(
            title=f"Unread Emails ({len(emails)})",
            color=discord.Color.red(),
        )
        for i, email in enumerate(emails, 1):
            embed.add_field(
                name="{}. {}".format(i, email["subject"]),
                value="From: {}".format(email["from"]),
                inline=False,
            )
        await ctx.send(embed=embed)

    @commands.command(name="mentions")
    async def mentions(self, ctx):
        """Check recent mentions in this server. Usage: !mentions"""
        mentions_found = await self._get_recent_mentions(ctx)

        if not mentions_found:
            await ctx.send("No recent mentions found.")
            return

        embed = discord.Embed(
            title=f"Recent Mentions ({len(mentions_found)})",
            color=discord.Color.purple(),
        )
        for i, m in enumerate(mentions_found[:10], 1):
            embed.add_field(
                name="{}. #{} — {} ({})".format(i, m["channel"], m["author"], m["created_at"]),
                value=m["content"],
                inline=False,
            )
        await ctx.send(embed=embed)

    @commands.command(name="notifications")
    async def notifications(self, ctx):
        """Combined: unread emails + Discord mentions. Usage: !notifications"""
        emails = await get_unread_emails()
        mentions_found = await self._get_recent_mentions(ctx)

        embed = discord.Embed(title="Notifications", color=discord.Color.dark_orange())

        # Email section
        if emails is None:
            embed.add_field(name="Email", value="Gmail not configured", inline=False)
        elif not emails:
            embed.add_field(name="Email", value="No unread emails", inline=False)
        else:
            email_lines = ["**{}** from {}".format(e["subject"], e["from"]) for e in emails[:5]]
            embed.add_field(
                name=f"Unread Emails ({len(emails)})",
                value="\n".join(email_lines),
                inline=False,
            )

        # Mentions section
        if not mentions_found:
            embed.add_field(
                name="Discord Mentions",
                value="No recent mentions",
                inline=False,
            )
        else:
            mention_lines = [
                "**#{}** — {}: {}".format(m["channel"], m["author"], m["content"][:50])
                for m in mentions_found[:5]
            ]
            embed.add_field(
                name=f"Discord Mentions ({len(mentions_found)})",
                value="\n".join(mention_lines),
                inline=False,
            )

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Notifications(bot))
