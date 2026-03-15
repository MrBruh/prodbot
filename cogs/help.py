import discord
from discord.ext import commands


class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.remove_command("help")

    @commands.command(name="help")
    async def help_command(self, ctx):
        """Show all available commands."""
        embed = discord.Embed(
            title="Productivity Bot — Commands",
            color=discord.Color.blurple(),
        )

        embed.add_field(
            name="Links",
            value=(
                "`!save <url> [tags]` — Save a link\n"
                "`!links [unread|read|all]` — List saved links\n"
                "`!read <id>` — Mark a link as read"
            ),
            inline=False,
        )

        embed.add_field(
            name="Todos",
            value=(
                "`!todo add <task>` — Add a task for today\n"
                "`!todo` / `!today` — Show today's tasks\n"
                "`!todo done <id>` — Mark a task complete\n"
                "`!todo date <YYYY-MM-DD>` — View tasks for a date"
            ),
            inline=False,
        )

        embed.add_field(
            name="Bucket List",
            value=(
                "`!goal add <goal> #category` — Add a long-term goal\n"
                "`!goals` — Show all goals by category\n"
                "`!goal progress <id>` — Mark goal as in-progress\n"
                "`!goal done <id>` — Mark goal as complete"
            ),
            inline=False,
        )

        embed.add_field(
            name="Journal",
            value=(
                "`!log <entry>` — Log a journal entry for today\n"
                "`!journal [date]` — View journal entries\n"
                "`!reflect` — Claude summarizes your day"
            ),
            inline=False,
        )

        embed.add_field(
            name="Reminders",
            value=(
                "`!remind at <time> <message>` — Set a timed reminder\n"
                "`!remind before <context> <message>` — Set a context reminder\n"
                "`!remind morning <message>` — Remind at morning context\n"
                "`!remind remove <id>` — Remove a reminder by ID\n"
                "`!heading out` / `!leaving` — Show heading-out reminders\n"
                "`!reminders` — List all active reminders"
            ),
            inline=False,
        )

        embed.add_field(
            name="Notifications",
            value=(
                "`!email check` — Show unread emails\n"
                "`!mentions` — Check recent Discord mentions\n"
                "`!notifications` — Combined email + mentions"
            ),
            inline=False,
        )

        embed.set_footer(text="Or just type naturally — Claude will figure out the intent!")

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Help(bot))
