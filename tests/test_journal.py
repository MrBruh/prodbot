"""Tests for the Journal cog."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest
import pytest_asyncio

import database
from cogs.journal import Journal, _dict_factory


class AsyncContextManagerMock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


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
    return Journal(bot)


@pytest.fixture
def ctx():
    mock_ctx = MagicMock()
    mock_ctx.send = AsyncMock()
    mock_ctx.typing = MagicMock(return_value=AsyncContextManagerMock())
    return mock_ctx


def _patch_get_db(db_path):
    def fake_get_db():
        return aiosqlite.connect(db_path)

    return patch("cogs.journal.get_db", side_effect=fake_get_db)


# ── log command ─────────────────────────────────────────────────────────────


class TestLogEntry:
    @pytest.mark.asyncio
    async def test_log_inserts_for_today(self, cog, ctx, db_path):
        today = str(date.today())
        with _patch_get_db(db_path):
            await cog.log_entry.callback(cog, ctx, entry="Worked on tests today")

        async with aiosqlite.connect(db_path) as db:
            db.row_factory = _dict_factory
            cur = await db.execute("SELECT * FROM journal WHERE id = 1")
            row = await cur.fetchone()

        assert row is not None
        assert row["date"] == today
        assert row["entry"] == "Worked on tests today"
        ctx.send.assert_called_once_with("Logged for today.")


# ── journal (view) command ──────────────────────────────────────────────────


class TestViewJournal:
    @pytest.mark.asyncio
    async def test_journal_retrieves_by_date(self, cog, ctx, db_path):
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO journal (date, entry, created_at) VALUES (?, ?, ?)",
                ("2025-03-20", "Entry for 3/20", "2025-03-20 10:30:00"),
            )
            await db.execute(
                "INSERT INTO journal (date, entry, created_at) VALUES (?, ?, ?)",
                ("2025-03-21", "Entry for 3/21", "2025-03-21 10:30:00"),
            )
            await db.commit()

        with _patch_get_db(db_path):
            await cog.view_journal.callback(cog, ctx, target_date="2025-03-20")

        ctx.send.assert_called_once()
        embed = ctx.send.call_args[1]["embed"]
        assert "2025-03-20" in embed.title
        assert embed.fields[0].value == "Entry for 3/20"

    @pytest.mark.asyncio
    async def test_journal_defaults_to_today(self, cog, ctx, db_path):
        today = str(date.today())
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO journal (date, entry, created_at) VALUES (?, ?, ?)",
                (today, "Today entry", f"{today} 09:00:00"),
            )
            await db.commit()

        with _patch_get_db(db_path):
            await cog.view_journal.callback(cog, ctx, target_date=None)

        ctx.send.assert_called_once()
        embed = ctx.send.call_args[1]["embed"]
        assert today in embed.title

    @pytest.mark.asyncio
    async def test_journal_no_entries(self, cog, ctx, db_path):
        with _patch_get_db(db_path):
            await cog.view_journal.callback(cog, ctx, target_date="2099-01-01")

        ctx.send.assert_called_once_with("No journal entries for 2099-01-01.")

    @pytest.mark.asyncio
    async def test_multiple_entries_same_date(self, cog, ctx, db_path):
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO journal (date, entry, created_at) VALUES (?, ?, ?)",
                ("2025-03-20", "Morning entry", "2025-03-20 09:00:00"),
            )
            await db.execute(
                "INSERT INTO journal (date, entry, created_at) VALUES (?, ?, ?)",
                ("2025-03-20", "Evening entry", "2025-03-20 20:00:00"),
            )
            await db.commit()

        with _patch_get_db(db_path):
            await cog.view_journal.callback(cog, ctx, target_date="2025-03-20")

        ctx.send.assert_called_once()
        embed = ctx.send.call_args[1]["embed"]
        assert len(embed.fields) == 2
        assert embed.fields[0].value == "Morning entry"
        assert embed.fields[1].value == "Evening entry"


# ── reflect command ─────────────────────────────────────────────────────────


class TestReflect:
    @pytest.mark.asyncio
    async def test_reflect_with_no_data_returns_early(self, cog, ctx, db_path):
        with _patch_get_db(db_path):
            await cog.reflect.callback(cog, ctx)

        ctx.send.assert_called_once_with(
            "Nothing to reflect on yet — add some tasks or journal entries first."
        )

    @pytest.mark.asyncio
    async def test_reflect_with_todos_but_no_journal(self, cog, ctx, db_path):
        today = str(date.today())
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO todos (date, task, completed) VALUES (?, ?, ?)",
                (today, "Write tests", 1),
            )
            await db.commit()

        with _patch_get_db(db_path), patch(
            "cogs.journal.reflect_on_day",
            new_callable=AsyncMock,
            return_value="Great day! You completed your testing tasks.",
        ):
            await cog.reflect.callback(cog, ctx)

        # Should have called send with an embed containing the reflection
        ctx.send.assert_called_once()
        embed = ctx.send.call_args[1]["embed"]
        assert "Reflection" in embed.title
        assert "Great day" in embed.description

    @pytest.mark.asyncio
    async def test_reflect_with_journal_but_no_todos(self, cog, ctx, db_path):
        today = str(date.today())
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO journal (date, entry, created_at) VALUES (?, ?, ?)",
                (today, "Feeling good", f"{today} 10:00:00"),
            )
            await db.commit()

        with _patch_get_db(db_path), patch(
            "cogs.journal.reflect_on_day",
            new_callable=AsyncMock,
            return_value="You had a positive day!",
        ):
            await cog.reflect.callback(cog, ctx)

        ctx.send.assert_called_once()
        embed = ctx.send.call_args[1]["embed"]
        assert "Reflection" in embed.title
        assert "positive" in embed.description
