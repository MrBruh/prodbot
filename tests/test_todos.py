"""Tests for the Todos cog."""

import pytest
import pytest_asyncio
import aiosqlite
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date

import database
from cogs.todos import Todos, _dict_factory


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
    return Todos(bot)


@pytest.fixture
def ctx():
    mock_ctx = MagicMock()
    mock_ctx.send = AsyncMock()
    return mock_ctx


def _patch_get_db(db_path):
    def fake_get_db():
        return aiosqlite.connect(db_path)

    return patch("cogs.todos.get_db", side_effect=fake_get_db)


# ── todo add ────────────────────────────────────────────────────────────────


class TestTodoAdd:
    @pytest.mark.asyncio
    async def test_add_inserts_for_today(self, cog, ctx, db_path):
        today = str(date.today())
        with _patch_get_db(db_path):
            await cog.todo_add.callback(cog, ctx, task="Write unit tests")

        async with aiosqlite.connect(db_path) as db:
            db.row_factory = _dict_factory
            cur = await db.execute("SELECT * FROM todos WHERE id = 1")
            row = await cur.fetchone()

        assert row is not None
        assert row["date"] == today
        assert row["task"] == "Write unit tests"
        assert row["completed"] == 0
        ctx.send.assert_called_once()
        assert "Write unit tests" in ctx.send.call_args[0][0]


# ── todo done ───────────────────────────────────────────────────────────────


class TestTodoDone:
    @pytest.mark.asyncio
    async def test_done_flips_completed(self, cog, ctx, db_path):
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO todos (date, task) VALUES (?, ?)",
                (str(date.today()), "Task"),
            )
            await db.commit()

        with _patch_get_db(db_path):
            await cog.todo_done.callback(cog, ctx, task_id=1)

        async with aiosqlite.connect(db_path) as db:
            db.row_factory = _dict_factory
            cur = await db.execute("SELECT completed FROM todos WHERE id = 1")
            row = await cur.fetchone()

        assert row["completed"] == 1
        ctx.send.assert_called_once_with("Task #1 marked as done!")

    @pytest.mark.asyncio
    async def test_done_nonexistent_id_returns_error(self, cog, ctx, db_path):
        with _patch_get_db(db_path):
            await cog.todo_done.callback(cog, ctx, task_id=999)

        ctx.send.assert_called_once_with("No task found with ID 999.")


# ── todo date ───────────────────────────────────────────────────────────────


class TestTodoDate:
    @pytest.mark.asyncio
    async def test_date_filters_correctly(self, cog, ctx, db_path):
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO todos (date, task) VALUES (?, ?)",
                ("2025-03-20", "Task A"),
            )
            await db.execute(
                "INSERT INTO todos (date, task) VALUES (?, ?)",
                ("2025-03-21", "Task B"),
            )
            await db.commit()

        with _patch_get_db(db_path):
            await cog.todo_date.callback(cog, ctx, target_date="2025-03-20")

        ctx.send.assert_called_once()
        embed = ctx.send.call_args[1]["embed"]
        assert "2025-03-20" in embed.title
        assert "Task A" in embed.description

    @pytest.mark.asyncio
    async def test_empty_date_shows_message(self, cog, ctx, db_path):
        with _patch_get_db(db_path):
            await cog.todo_date.callback(cog, ctx, target_date="2025-01-01")

        ctx.send.assert_called_once_with("No tasks for 2025-01-01.")


# ── _show_tasks progress ───────────────────────────────────────────────────


class TestShowTasks:
    @pytest.mark.asyncio
    async def test_progress_calculation(self, cog, ctx, db_path):
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO todos (date, task, completed) VALUES (?, ?, ?)",
                ("2025-03-20", "Done task", 1),
            )
            await db.execute(
                "INSERT INTO todos (date, task, completed) VALUES (?, ?, ?)",
                ("2025-03-20", "Pending task", 0),
            )
            await db.commit()

        with _patch_get_db(db_path):
            await cog._show_tasks(ctx, "2025-03-20")

        embed = ctx.send.call_args[1]["embed"]
        assert "1/2" in embed.footer.text
        assert "50%" in embed.footer.text

    @pytest.mark.asyncio
    async def test_empty_state(self, cog, ctx, db_path):
        with _patch_get_db(db_path):
            await cog._show_tasks(ctx, "2099-01-01")

        ctx.send.assert_called_once_with("No tasks for 2099-01-01.")


# ── today alias ─────────────────────────────────────────────────────────────


class TestTodayAlias:
    @pytest.mark.asyncio
    async def test_today_shows_todays_tasks(self, cog, ctx, db_path):
        today = str(date.today())
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO todos (date, task) VALUES (?, ?)",
                (today, "Today task"),
            )
            await db.commit()

        with _patch_get_db(db_path):
            await cog.today.callback(cog, ctx)

        ctx.send.assert_called_once()
        embed = ctx.send.call_args[1]["embed"]
        assert today in embed.title
        assert "Today task" in embed.description
