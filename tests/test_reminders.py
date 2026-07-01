"""Tests for the Reminders cog."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest
import pytest_asyncio

import database
from cogs.reminders import Reminders, _dict_factory
from services.timeutil import now as tz_now


@pytest_asyncio.fixture
async def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    original = database.DB_PATH
    database.DB_PATH = path
    await database.init_db()
    yield path
    database.DB_PATH = original


@pytest.fixture
def bot():
    return MagicMock()


@pytest.fixture
def cog(bot):
    with patch("cogs.reminders.start_scheduler"):
        return Reminders(bot)


@pytest.fixture
def ctx():
    mock_ctx = MagicMock()
    mock_ctx.send = AsyncMock()
    mock_ctx.channel = MagicMock()
    mock_ctx.channel.id = 12345
    mock_ctx.author = MagicMock()
    mock_ctx.author.id = 99999
    mock_ctx.message = MagicMock()
    mock_ctx.message.mentions = []
    return mock_ctx


def _patch_get_db(db_path):
    def fake_get_db():
        return aiosqlite.connect(db_path)

    return patch("cogs.reminders.get_db", new_callable=MagicMock, side_effect=fake_get_db)


# ── create_reminder (shared helper) ────────────────────────────────────────


class TestCreateReminder:
    @pytest.mark.asyncio
    async def test_timed_inserts_and_schedules(self, cog, ctx, db_path):
        with _patch_get_db(db_path), patch("cogs.reminders.scheduler") as mock_scheduler:
            created = await cog.create_reminder(
                ctx, message="Call Sarah", remind_at="2026-06-30T21:00:00"
            )

        assert created is True
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = _dict_factory
            row = await (await db.execute("SELECT * FROM reminders WHERE id = 1")).fetchone()

        assert row["message"] == "Call Sarah"
        assert row["remind_at"] == "2026-06-30T21:00:00"
        assert row["user_id"] == 99999
        assert row["target_user_id"] == 99999
        mock_scheduler.add_job.assert_called_once()
        embed = ctx.send.call_args[1]["embed"]
        assert "Call Sarah" in embed.description

    @pytest.mark.asyncio
    async def test_context_inserts_without_scheduling(self, cog, ctx, db_path):
        with _patch_get_db(db_path), patch("cogs.reminders.scheduler") as mock_scheduler:
            created = await cog.create_reminder(ctx, message="Grab keys", context="heading_out")

        assert created is True
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = _dict_factory
            row = await (await db.execute("SELECT * FROM reminders WHERE id = 1")).fetchone()

        assert row["message"] == "Grab keys"
        assert row["context"] == "heading_out"
        assert row["remind_at"] is None
        mock_scheduler.add_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_target_other_user(self, cog, ctx, db_path):
        target = MagicMock()
        target.id = 88888
        target.mention = "<@88888>"

        with _patch_get_db(db_path):
            await cog.create_reminder(
                ctx, message="Bring the cake", context="heading_out", target=target
            )

        async with aiosqlite.connect(db_path) as db:
            db.row_factory = _dict_factory
            row = await (await db.execute("SELECT * FROM reminders WHERE id = 1")).fetchone()

        assert row["user_id"] == 99999  # author
        assert row["target_user_id"] == 88888  # reminded user
        embed = ctx.send.call_args[1]["embed"]
        assert "For: <@88888>" in embed.description

    @pytest.mark.asyncio
    async def test_empty_message_rejected(self, cog, ctx, db_path):
        with _patch_get_db(db_path):
            created = await cog.create_reminder(ctx, message="   ", context="heading_out")

        assert created is False
        async with aiosqlite.connect(db_path) as db:
            count = (await (await db.execute("SELECT COUNT(*) FROM reminders")).fetchone())[0]
        assert count == 0
        ctx.send.assert_called_once()


# ── remind before (context-based) ─────────────────────────────────────────


class TestRemindBefore:
    @pytest.mark.asyncio
    async def test_add_context_reminder(self, cog, ctx, db_path):
        with _patch_get_db(db_path):
            await cog.remind_before.callback(
                cog, ctx, context="heading_out", message="Grab package"
            )

        async with aiosqlite.connect(db_path) as db:
            db.row_factory = _dict_factory
            cur = await db.execute("SELECT * FROM reminders WHERE id = 1")
            row = await cur.fetchone()

        assert row is not None
        assert row["message"] == "Grab package"
        assert row["context"] == "heading_out"
        assert row["fired"] == 0
        ctx.send.assert_called_once()
        embed = ctx.send.call_args[1]["embed"]
        assert "Grab package" in embed.description
        assert "heading_out" in embed.description


# ── remind (timed via parse_reminder_time) ─────────────────────────────────


class TestRemindTimed:
    @pytest.mark.asyncio
    async def test_add_timed_reminder(self, cog, ctx, db_path):
        parsed = {
            "remind_at": "2026-03-15T21:00:00",
            "context": None,
            "message": "Call Sarah",
        }
        with _patch_get_db(db_path), patch(
            "cogs.reminders.parse_reminder_time", new_callable=AsyncMock, return_value=parsed
        ), patch("cogs.reminders.scheduler") as mock_scheduler:
            await cog.remind.callback(cog, ctx, text="at 9pm Call Sarah")

        async with aiosqlite.connect(db_path) as db:
            db.row_factory = _dict_factory
            cur = await db.execute("SELECT * FROM reminders WHERE id = 1")
            row = await cur.fetchone()

        assert row is not None
        assert row["message"] == "Call Sarah"
        assert row["remind_at"] == "2026-03-15T21:00:00"
        assert row["fired"] == 0
        mock_scheduler.add_job.assert_called_once()
        ctx.send.assert_called_once()
        embed = ctx.send.call_args[1]["embed"]
        assert "Call Sarah" in embed.description

    @pytest.mark.asyncio
    async def test_add_context_reminder_via_parse(self, cog, ctx, db_path):
        parsed = {
            "remind_at": None,
            "context": "heading_out",
            "message": "Bring package",
        }
        with _patch_get_db(db_path), patch(
            "cogs.reminders.parse_reminder_time", new_callable=AsyncMock, return_value=parsed
        ):
            await cog.remind.callback(cog, ctx, text="before heading_out Bring package")

        async with aiosqlite.connect(db_path) as db:
            db.row_factory = _dict_factory
            cur = await db.execute("SELECT * FROM reminders WHERE id = 1")
            row = await cur.fetchone()

        assert row is not None
        assert row["message"] == "Bring package"
        assert row["context"] == "heading_out"
        ctx.send.assert_called_once()


# ── heading out ────────────────────────────────────────────────────────────


class TestHeadingOut:
    @pytest.mark.asyncio
    async def test_heading_out_shows_and_fires_reminders(self, cog, ctx, db_path):
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO reminders (message, context) VALUES (?, ?)",
                ("Grab package", "heading_out"),
            )
            await db.execute(
                "INSERT INTO reminders (message, context) VALUES (?, ?)",
                ("Take umbrella", "heading_out"),
            )
            await db.commit()

        with _patch_get_db(db_path):
            await cog.heading_out.callback(cog, ctx)

        ctx.send.assert_called_once()
        embed = ctx.send.call_args[1]["embed"]
        assert "Grab package" in embed.description
        assert "Take umbrella" in embed.description

        # Verify they are deleted
        async with aiosqlite.connect(db_path) as db:
            cur = await db.execute("SELECT COUNT(*) FROM reminders")
            count = (await cur.fetchone())[0]

        assert count == 0

    @pytest.mark.asyncio
    async def test_heading_out_no_reminders(self, cog, ctx, db_path):
        with _patch_get_db(db_path):
            await cog.heading_out.callback(cog, ctx)

        ctx.send.assert_called_once()
        embed = ctx.send.call_args[1]["embed"]
        assert "No" in embed.title or "No" in embed.description


# ── reminders list ─────────────────────────────────────────────────────────


class TestListReminders:
    @pytest.mark.asyncio
    async def test_list_active_reminders(self, cog, ctx, db_path):
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO reminders (message, context) VALUES (?, ?)",
                ("Grab package", "heading_out"),
            )
            await db.execute(
                "INSERT INTO reminders (message, remind_at) VALUES (?, ?)",
                ("Call Sarah", "2026-03-15T21:00:00"),
            )
            await db.commit()

        with _patch_get_db(db_path):
            await cog.list_reminders.callback(cog, ctx)

        ctx.send.assert_called_once()
        embed = ctx.send.call_args[1]["embed"]
        assert "Grab package" in embed.description
        assert "Call Sarah" in embed.description

    @pytest.mark.asyncio
    async def test_list_no_active_reminders(self, cog, ctx, db_path):
        with _patch_get_db(db_path):
            await cog.list_reminders.callback(cog, ctx)

        ctx.send.assert_called_once()
        embed = ctx.send.call_args[1]["embed"]
        assert "No active reminders" in embed.description


# ── remind morning ─────────────────────────────────────────────────────────


class TestRemindMorning:
    @pytest.mark.asyncio
    async def test_morning_sets_context(self, cog, ctx, db_path):
        with _patch_get_db(db_path):
            await cog.remind_morning.callback(cog, ctx, message="Take vitamins")

        async with aiosqlite.connect(db_path) as db:
            db.row_factory = _dict_factory
            cur = await db.execute("SELECT * FROM reminders WHERE id = 1")
            row = await cur.fetchone()

        assert row is not None
        assert row["message"] == "Take vitamins"
        assert row["context"] == "morning"
        ctx.send.assert_called_once()
        embed = ctx.send.call_args[1]["embed"]
        assert "Take vitamins" in embed.description
        assert "morning" in embed.description


# ── missed reminders on startup ───────────────────────────────────────────


class TestMissedReminders:
    @pytest.mark.asyncio
    async def test_fires_missed_reminders_on_startup(self, cog, bot, db_path):
        past_time = (tz_now() - timedelta(minutes=10)).isoformat()
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO reminders (message, remind_at, user_id, target_user_id, channel_id) VALUES (?, ?, ?, ?, ?)",
                ("Missed one", past_time, 99999, 99999, 12345),
            )
            await db.commit()

        mock_channel = MagicMock()
        mock_channel.send = AsyncMock()
        bot.get_channel = MagicMock(return_value=mock_channel)
        bot.wait_until_ready = AsyncMock()

        with _patch_get_db(db_path):
            await cog._reschedule_reminders()

        mock_channel.send.assert_called_once()
        embed = mock_channel.send.call_args[1]["embed"]
        assert "Missed one" in embed.description
        assert mock_channel.send.call_args[1]["content"] == "<@99999>"

        # Verify deleted from DB
        async with aiosqlite.connect(db_path) as db:
            cur = await db.execute("SELECT COUNT(*) FROM reminders")
            count = (await cur.fetchone())[0]
        assert count == 0

    @pytest.mark.asyncio
    async def test_no_missed_reminders(self, cog, bot, db_path):
        bot.wait_until_ready = AsyncMock()
        bot.get_channel = MagicMock()

        with _patch_get_db(db_path):
            await cog._reschedule_reminders()

        bot.get_channel.assert_not_called()

    @pytest.mark.asyncio
    async def test_future_reminder_is_rescheduled_not_fired(self, cog, bot, db_path):
        """Regression (#6): a not-yet-due reminder must be rescheduled, not fired."""
        future_time = (tz_now() + timedelta(hours=2)).isoformat()
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO reminders (message, remind_at, user_id, target_user_id, channel_id) VALUES (?, ?, ?, ?, ?)",
                ("Vacuum the floor", future_time, 99999, 99999, 12345),
            )
            await db.commit()

        bot.wait_until_ready = AsyncMock()
        bot.get_channel = MagicMock()

        with _patch_get_db(db_path), patch("cogs.reminders.scheduler") as mock_scheduler:
            await cog._reschedule_reminders()

        # Not fired as "missed"...
        bot.get_channel.assert_not_called()
        # ...but scheduled for later, and left in the DB.
        mock_scheduler.add_job.assert_called_once()
        async with aiosqlite.connect(db_path) as db:
            count = (await (await db.execute("SELECT COUNT(*) FROM reminders")).fetchone())[0]
        assert count == 1
