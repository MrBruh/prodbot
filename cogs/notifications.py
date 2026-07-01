import logging
from typing import Dict, List

import discord
from discord.ext import commands

from services.gmail_oauth import create_pending
from services.gmail_service import (
    delete_account,
    get_account,
    get_unread_emails,
    gmail_configured,
)

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
        """Email commands. Usage: !email register | !email check | !email forget"""
        await ctx.send("Usage: `!email register` · `!email check` · `!email forget`")

    @email.command(name="register")
    async def email_register(self, ctx):
        """Connect your Gmail (read-only) so the bot can check it for you."""
        if not gmail_configured():
            await ctx.send("Email isn't set up on this bot yet.")
            return

        auth_url = create_pending(ctx.author.id)
        embed = discord.Embed(
            title="Connect your Gmail",
            description=(
                "Click below to grant **read-only** access — the bot only ever reads the "
                "sender and subject of your unread mail, never the contents.\n\n"
                f"**[Authorize with Google]({auth_url})**\n\n"
                "This link is personal to you and expires in 10 minutes."
            ),
            color=discord.Color.blurple(),
        )
        try:
            await ctx.author.send(embed=embed)
        except discord.Forbidden:
            await ctx.send(
                "I couldn't DM you — enable **Direct Messages** from server members "
                "(Privacy Settings) and run `!email register` again."
            )
            return

        if ctx.guild is not None:
            await ctx.send(
                "📬 Check your DMs — I've sent you a private link to connect your email."
            )

    @email.command(name="check")
    async def email_check(self, ctx):
        """Show your unread emails. Usage: !email check"""
        if not gmail_configured():
            await ctx.send("Email isn't set up on this bot yet.")
            return
        if not await get_account(ctx.author.id):
            await ctx.send(
                "You haven't connected an email yet. Run `!email register` to link your Gmail."
            )
            return

        async with ctx.typing():
            emails = await get_unread_emails(ctx.author.id)

        if emails is None:
            await ctx.send(
                "I couldn't reach your Gmail — your access may have expired. "
                "Run `!email register` to reconnect."
            )
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

    @email.command(name="forget")
    async def email_forget(self, ctx):
        """Disconnect your Gmail from the bot. Usage: !email forget"""
        if await delete_account(ctx.author.id):
            await ctx.send("Disconnected your email — the bot no longer has access.")
        else:
            await ctx.send("You don't have an email connected.")

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
        """Combined: your unread emails + Discord mentions. Usage: !notifications"""
        registered = gmail_configured() and bool(await get_account(ctx.author.id))
        emails = await get_unread_emails(ctx.author.id) if registered else None
        mentions_found = await self._get_recent_mentions(ctx)

        embed = discord.Embed(title="Notifications", color=discord.Color.dark_orange())

        # Email section
        if not registered:
            embed.add_field(
                name="Email", value="Not connected — run `!email register`", inline=False
            )
        elif emails is None:
            embed.add_field(
                name="Email",
                value="Couldn't reach Gmail — try `!email register` again",
                inline=False,
            )
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
