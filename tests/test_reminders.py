"""Tests for the Reminders cog."""

from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest
import pytest_asyncio

import database
from cogs.reminders import Reminders, _dict_factory


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
    return mock_ctx


def _patch_get_db(db_path):
    def fake_get_db():
        return aiosqlite.connect(db_path)

    return patch("cogs.reminders.get_db", new_callable=MagicMock, side_effect=fake_get_db)


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

        # Verify they are marked as fired
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = _dict_factory
            cur = await db.execute("SELECT * FROM reminders WHERE fired = 0")
            unfired = await cur.fetchall()

        assert len(unfired) == 0

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
