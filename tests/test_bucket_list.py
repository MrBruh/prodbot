"""Tests for the BucketList cog."""

from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest
import pytest_asyncio

import database
from cogs.bucket_list import BucketList, _dict_factory


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
    return BucketList(bot)


@pytest.fixture
def ctx():
    mock_ctx = MagicMock()
    mock_ctx.send = AsyncMock()
    return mock_ctx


def _patch_get_db(db_path):
    def fake_get_db():
        return aiosqlite.connect(db_path)

    return patch("cogs.bucket_list.get_db", side_effect=fake_get_db)


# ── goal add ────────────────────────────────────────────────────────────────


class TestGoalAdd:
    @pytest.mark.asyncio
    async def test_add_with_category(self, cog, ctx, db_path):
        with _patch_get_db(db_path):
            await cog.goal_add.callback(cog, ctx, text="Learn Rust #learning")

        async with aiosqlite.connect(db_path) as db:
            db.row_factory = _dict_factory
            cur = await db.execute("SELECT * FROM bucket_list WHERE id = 1")
            row = await cur.fetchone()

        assert row["goal"] == "Learn Rust"
        assert row["category"] == "learning"
        ctx.send.assert_called_once()
        assert "Learn Rust" in ctx.send.call_args[0][0]
        assert "learning" in ctx.send.call_args[0][0]

    @pytest.mark.asyncio
    async def test_add_without_category_defaults_to_general(self, cog, ctx, db_path):
        with _patch_get_db(db_path):
            await cog.goal_add.callback(cog, ctx, text="Run a marathon")

        async with aiosqlite.connect(db_path) as db:
            db.row_factory = _dict_factory
            cur = await db.execute("SELECT * FROM bucket_list WHERE id = 1")
            row = await cur.fetchone()

        assert row["goal"] == "Run a marathon"
        assert row["category"] == "general"


# ── goal progress ───────────────────────────────────────────────────────────


class TestGoalProgress:
    @pytest.mark.asyncio
    async def test_progress_transitions_status(self, cog, ctx, db_path):
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO bucket_list (goal, category) VALUES (?, ?)",
                ("Goal", "general"),
            )
            await db.commit()

        with _patch_get_db(db_path):
            await cog.goal_progress.callback(cog, ctx, goal_id=1)

        async with aiosqlite.connect(db_path) as db:
            db.row_factory = _dict_factory
            cur = await db.execute("SELECT status FROM bucket_list WHERE id = 1")
            row = await cur.fetchone()

        assert row["status"] == "in_progress"
        ctx.send.assert_called_once_with("Goal #1 marked as in-progress.")

    @pytest.mark.asyncio
    async def test_progress_nonexistent_id(self, cog, ctx, db_path):
        with _patch_get_db(db_path):
            await cog.goal_progress.callback(cog, ctx, goal_id=999)

        ctx.send.assert_called_once_with("No goal found with ID 999.")


# ── goal done ───────────────────────────────────────────────────────────────


class TestGoalDone:
    @pytest.mark.asyncio
    async def test_done_sets_status_and_completed_at(self, cog, ctx, db_path):
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO bucket_list (goal, category) VALUES (?, ?)",
                ("Goal", "general"),
            )
            await db.commit()

        with _patch_get_db(db_path):
            await cog.goal_done.callback(cog, ctx, goal_id=1)

        async with aiosqlite.connect(db_path) as db:
            db.row_factory = _dict_factory
            cur = await db.execute("SELECT status, completed_at FROM bucket_list WHERE id = 1")
            row = await cur.fetchone()

        assert row["status"] == "done"
        assert row["completed_at"] is not None
        ctx.send.assert_called_once_with("Goal #1 completed!")

    @pytest.mark.asyncio
    async def test_done_nonexistent_id(self, cog, ctx, db_path):
        with _patch_get_db(db_path):
            await cog.goal_done.callback(cog, ctx, goal_id=999)

        ctx.send.assert_called_once_with("No goal found with ID 999.")


# ── _show_goals ─────────────────────────────────────────────────────────────


class TestShowGoals:
    @pytest.mark.asyncio
    async def test_empty_goals(self, cog, ctx, db_path):
        with _patch_get_db(db_path):
            await cog._show_goals(ctx)

        ctx.send.assert_called_once_with("No goals yet. Add one with `!goal add <goal> #category`")

    @pytest.mark.asyncio
    async def test_goals_grouped_by_category(self, cog, ctx, db_path):
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO bucket_list (goal, category) VALUES (?, ?)",
                ("Learn Rust", "learning"),
            )
            await db.execute(
                "INSERT INTO bucket_list (goal, category) VALUES (?, ?)",
                ("Run marathon", "fitness"),
            )
            await db.execute(
                "INSERT INTO bucket_list (goal, category) VALUES (?, ?)",
                ("Read more books", "learning"),
            )
            await db.commit()

        with _patch_get_db(db_path):
            await cog._show_goals(ctx)

        ctx.send.assert_called_once()
        embed = ctx.send.call_args[1]["embed"]
        # Should have fields for 'fitness' and 'learning'
        field_names = [f.name for f in embed.fields]
        assert "Learning" in field_names or "learning" in [n.lower() for n in field_names]
        assert "Fitness" in field_names or "fitness" in [n.lower() for n in field_names]

        # learning field should contain both goals
        for f in embed.fields:
            if f.name.lower() == "learning":
                assert "Learn Rust" in f.value
                assert "Read more books" in f.value


# ── goals alias ─────────────────────────────────────────────────────────────


class TestGoalsAlias:
    @pytest.mark.asyncio
    async def test_goals_alias_shows_all(self, cog, ctx, db_path):
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO bucket_list (goal, category) VALUES (?, ?)",
                ("Goal A", "general"),
            )
            await db.commit()

        with _patch_get_db(db_path):
            await cog.goals.callback(cog, ctx)

        ctx.send.assert_called_once()
        embed = ctx.send.call_args[1]["embed"]
        assert "Bucket List" in embed.title
