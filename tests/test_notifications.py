"""Tests for the Notifications cog."""

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from cogs.notifications import Notifications


class AsyncContextMock:
    """Mock for async context managers (e.g. ctx.typing())."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class AsyncIterator:
    """Mock for async iterators (e.g. channel.history())."""

    def __init__(self, items):
        self.items = list(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.items:
            raise StopAsyncIteration
        return self.items.pop(0)


@pytest.fixture
def bot():
    return MagicMock()


@pytest.fixture
def cog(bot):
    return Notifications(bot)


@pytest.fixture
def ctx():
    mock_ctx = MagicMock()
    mock_ctx.send = AsyncMock()
    mock_ctx.typing = MagicMock(return_value=AsyncContextMock())
    mock_ctx.guild = MagicMock()
    mock_ctx.guild.text_channels = []
    mock_ctx.author = MagicMock()
    mock_ctx.author.id = 42
    mock_ctx.author.send = AsyncMock()
    return mock_ctx


# --- email check tests -------------------------------------------------------


@pytest.mark.asyncio
@patch("cogs.notifications.gmail_configured", return_value=False)
async def test_email_check_not_configured(_mock_configured, cog, ctx):
    """!email check when the bot has no OAuth client configured."""
    await cog.email_check.callback(cog, ctx)

    ctx.send.assert_called_once()
    assert "isn't set up" in ctx.send.call_args[0][0]


@pytest.mark.asyncio
@patch("cogs.notifications.get_account", new_callable=AsyncMock)
@patch("cogs.notifications.gmail_configured", return_value=True)
async def test_email_check_not_registered(_mock_configured, mock_get_account, cog, ctx):
    """!email check when the user hasn't linked an account."""
    mock_get_account.return_value = None

    await cog.email_check.callback(cog, ctx)

    ctx.send.assert_called_once()
    assert "register" in ctx.send.call_args[0][0]


@pytest.mark.asyncio
@patch("cogs.notifications.get_unread_emails", new_callable=AsyncMock)
@patch("cogs.notifications.get_account", new_callable=AsyncMock)
@patch("cogs.notifications.gmail_configured", return_value=True)
async def test_email_check_fetch_failed(_cfg, mock_get_account, mock_get_emails, cog, ctx):
    """!email check when the fetch returns None (expired/revoked access)."""
    mock_get_account.return_value = {"refresh_token": "r"}
    mock_get_emails.return_value = None

    await cog.email_check.callback(cog, ctx)

    ctx.send.assert_called_once()
    assert "couldn't reach" in ctx.send.call_args[0][0].lower()


@pytest.mark.asyncio
@patch("cogs.notifications.get_unread_emails", new_callable=AsyncMock)
@patch("cogs.notifications.get_account", new_callable=AsyncMock)
@patch("cogs.notifications.gmail_configured", return_value=True)
async def test_email_check_no_unread(_cfg, mock_get_account, mock_get_emails, cog, ctx):
    """!email check with no unread emails."""
    mock_get_account.return_value = {"refresh_token": "r"}
    mock_get_emails.return_value = []

    await cog.email_check.callback(cog, ctx)

    ctx.send.assert_called_once()
    assert "No unread" in ctx.send.call_args[0][0]


@pytest.mark.asyncio
@patch("cogs.notifications.get_unread_emails", new_callable=AsyncMock)
@patch("cogs.notifications.get_account", new_callable=AsyncMock)
@patch("cogs.notifications.gmail_configured", return_value=True)
async def test_email_check_with_emails(_cfg, mock_get_account, mock_get_emails, cog, ctx):
    """!email check with unread emails renders an embed."""
    mock_get_account.return_value = {"refresh_token": "r"}
    mock_get_emails.return_value = [
        {"id": "1", "from": "alice@example.com", "subject": "Hello"},
        {"id": "2", "from": "bob@example.com", "subject": "Meeting"},
    ]

    await cog.email_check.callback(cog, ctx)

    ctx.send.assert_called_once()
    embed = ctx.send.call_args[1]["embed"]
    assert "Unread Emails (2)" in embed.title
    assert len(embed.fields) == 2
    assert "Hello" in embed.fields[0].name
    assert "alice@example.com" in embed.fields[0].value
    # The caller's own id is used for the lookup.
    mock_get_emails.assert_awaited_once_with(42)


# --- email register tests ----------------------------------------------------


@pytest.mark.asyncio
@patch("cogs.notifications.gmail_configured", return_value=False)
async def test_email_register_not_configured(_cfg, cog, ctx):
    await cog.email_register.callback(cog, ctx)

    ctx.send.assert_called_once()
    assert "isn't set up" in ctx.send.call_args[0][0]


@pytest.mark.asyncio
@patch("cogs.notifications.create_pending", return_value="https://accounts.google.com/auth?x=1")
@patch("cogs.notifications.gmail_configured", return_value=True)
async def test_email_register_dms_link(_cfg, mock_create_pending, cog, ctx):
    await cog.email_register.callback(cog, ctx)

    mock_create_pending.assert_called_once_with(42)
    ctx.author.send.assert_awaited_once()
    embed = ctx.author.send.call_args[1]["embed"]
    assert "accounts.google.com" in embed.description
    # A public nudge is sent in-channel too.
    ctx.send.assert_called_once()
    assert "DMs" in ctx.send.call_args[0][0]


@pytest.mark.asyncio
@patch("cogs.notifications.create_pending", return_value="https://accounts.google.com/auth")
@patch("cogs.notifications.gmail_configured", return_value=True)
async def test_email_register_dms_closed(_cfg, _create_pending, cog, ctx):
    ctx.author.send.side_effect = discord.Forbidden(MagicMock(status=403), "no dms")

    await cog.email_register.callback(cog, ctx)

    ctx.send.assert_called_once()
    assert "couldn't DM you" in ctx.send.call_args[0][0]


# --- email forget tests ------------------------------------------------------


@pytest.mark.asyncio
@patch("cogs.notifications.delete_account", new_callable=AsyncMock)
async def test_email_forget_removes(mock_delete, cog, ctx):
    mock_delete.return_value = True

    await cog.email_forget.callback(cog, ctx)

    mock_delete.assert_awaited_once_with(42)
    assert "Disconnected" in ctx.send.call_args[0][0]


@pytest.mark.asyncio
@patch("cogs.notifications.delete_account", new_callable=AsyncMock)
async def test_email_forget_nothing_connected(mock_delete, cog, ctx):
    mock_delete.return_value = False

    await cog.email_forget.callback(cog, ctx)

    assert "don't have an email" in ctx.send.call_args[0][0]


# --- mentions tests ----------------------------------------------------------


@pytest.mark.asyncio
async def test_mentions_no_mentions(cog, ctx):
    """Test !mentions with no mentions found."""
    ctx.guild.text_channels = []

    await cog.mentions.callback(cog, ctx)

    ctx.send.assert_called_once()
    assert "No recent mentions" in ctx.send.call_args[0][0]


@pytest.mark.asyncio
async def test_mentions_with_mentions(cog, ctx):
    """Test !mentions with mentions found."""
    author = ctx.author
    other_user = MagicMock()

    message = MagicMock()
    message.mentions = [author]
    message.author = other_user
    message.content = "Hey check this out"
    message.created_at = datetime.datetime(2026, 3, 15, 10, 30)

    channel = MagicMock()
    channel.name = "general"
    channel.history = MagicMock(return_value=AsyncIterator([message]))

    ctx.guild.text_channels = [channel]

    await cog.mentions.callback(cog, ctx)

    ctx.send.assert_called_once()
    embed = ctx.send.call_args[1]["embed"]
    assert "Recent Mentions (1)" in embed.title
    assert len(embed.fields) == 1
    assert "general" in embed.fields[0].name


@pytest.mark.asyncio
async def test_mentions_skips_own_messages(cog, ctx):
    """Test that mentions from the author themselves are skipped."""
    author = ctx.author

    message = MagicMock()
    message.mentions = [author]
    message.author = author  # same author
    message.content = "self-mention"
    message.created_at = datetime.datetime(2026, 3, 15, 10, 30)

    channel = MagicMock()
    channel.name = "general"
    channel.history = MagicMock(return_value=AsyncIterator([message]))

    ctx.guild.text_channels = [channel]

    await cog.mentions.callback(cog, ctx)

    ctx.send.assert_called_once()
    assert "No recent mentions" in ctx.send.call_args[0][0]


# --- notifications tests -----------------------------------------------------


@pytest.mark.asyncio
@patch("cogs.notifications.get_unread_emails", new_callable=AsyncMock)
@patch("cogs.notifications.get_account", new_callable=AsyncMock)
@patch("cogs.notifications.gmail_configured", return_value=True)
async def test_notifications_combined(_cfg, mock_get_account, mock_get_emails, cog, ctx):
    """Test !notifications combined output for a registered user."""
    mock_get_account.return_value = {"refresh_token": "r"}
    mock_get_emails.return_value = [
        {"id": "1", "from": "alice@example.com", "subject": "Hello"},
    ]
    ctx.guild.text_channels = []

    await cog.notifications.callback(cog, ctx)

    ctx.send.assert_called_once()
    embed = ctx.send.call_args[1]["embed"]
    assert embed.title == "Notifications"
    assert len(embed.fields) == 2
    assert "Unread Emails" in embed.fields[0].name
    assert "Discord Mentions" in embed.fields[1].name


@pytest.mark.asyncio
@patch("cogs.notifications.get_account", new_callable=AsyncMock)
@patch("cogs.notifications.gmail_configured", return_value=True)
async def test_notifications_not_registered(_cfg, mock_get_account, cog, ctx):
    """Test !notifications when the caller hasn't connected an email."""
    mock_get_account.return_value = None
    ctx.guild.text_channels = []

    await cog.notifications.callback(cog, ctx)

    embed = ctx.send.call_args[1]["embed"]
    assert "Not connected" in embed.fields[0].value


@pytest.mark.asyncio
@patch("cogs.notifications.get_unread_emails", new_callable=AsyncMock)
@patch("cogs.notifications.get_account", new_callable=AsyncMock)
@patch("cogs.notifications.gmail_configured", return_value=True)
async def test_notifications_no_emails_no_mentions(
    _cfg, mock_get_account, mock_get_emails, cog, ctx
):
    """Test !notifications with nothing to show."""
    mock_get_account.return_value = {"refresh_token": "r"}
    mock_get_emails.return_value = []
    ctx.guild.text_channels = []

    await cog.notifications.callback(cog, ctx)

    embed = ctx.send.call_args[1]["embed"]
    assert "No unread emails" in embed.fields[0].value
    assert "No recent mentions" in embed.fields[1].value


# --- email group tests -------------------------------------------------------


@pytest.mark.asyncio
async def test_email_group_no_subcommand(cog, ctx):
    """Test !email with no subcommand shows usage."""
    await cog.email.callback(cog, ctx)

    ctx.send.assert_called_once()
    assert "Usage" in ctx.send.call_args[0][0]
