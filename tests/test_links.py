"""Tests for the Links cog."""

from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest
import pytest_asyncio

import database
from cogs.links import Links, _dict_factory


@pytest_asyncio.fixture
async def db_path(tmp_path):
    """Temporary database with schema initialised."""
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
    return Links(bot)


@pytest.fixture
def ctx():
    mock_ctx = MagicMock()
    mock_ctx.send = AsyncMock()
    return mock_ctx


def _patch_get_db(db_path):
    """Return a patcher that makes cogs.links.get_db use our temp DB."""

    def fake_get_db():
        return aiosqlite.connect(db_path)

    return patch("cogs.links.get_db", side_effect=fake_get_db)


# ── save command ────────────────────────────────────────────────────────────


class TestSaveLink:
    @pytest.mark.asyncio
    async def test_save_inserts_row(self, cog, ctx, db_path):
        with _patch_get_db(db_path), patch(
            "cogs.links.summarize_url", new_callable=AsyncMock, return_value="Example Title"
        ):
            await cog.save_link.callback(cog, ctx, url="https://example.com", tags="python testing")

        # Verify row was inserted
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = _dict_factory
            cur = await db.execute("SELECT * FROM links WHERE id = 1")
            row = await cur.fetchone()

        assert row is not None
        assert row["url"] == "https://example.com"
        assert row["title"] == "Example Title"
        assert row["tags"] == "python testing"
        ctx.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_works_when_claude_api_fails(self, cog, ctx, db_path):
        with _patch_get_db(db_path), patch(
            "cogs.links.summarize_url",
            new_callable=AsyncMock,
            side_effect=Exception("API error"),
        ):
            await cog.save_link.callback(cog, ctx, url="https://fail.com", tags="")

        async with aiosqlite.connect(db_path) as db:
            db.row_factory = _dict_factory
            cur = await db.execute("SELECT * FROM links WHERE id = 1")
            row = await cur.fetchone()

        assert row is not None
        assert row["url"] == "https://fail.com"
        assert row["title"] is None
        ctx.send.assert_called_once()


# ── links (list) command ────────────────────────────────────────────────────


class TestListLinks:
    @pytest.mark.asyncio
    async def test_empty_db_shows_no_links(self, cog, ctx, db_path):
        with _patch_get_db(db_path):
            await cog.list_links.callback(cog, ctx, filter="unread")

        ctx.send.assert_called_once_with("No unread links found.")

    @pytest.mark.asyncio
    async def test_links_retrieves_unread(self, cog, ctx, db_path):
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO links (url, title, tags, read) VALUES (?, ?, ?, ?)",
                ("https://a.com", "A", "", 0),
            )
            await db.execute(
                "INSERT INTO links (url, title, tags, read) VALUES (?, ?, ?, ?)",
                ("https://b.com", "B", "", 1),
            )
            await db.commit()

        with _patch_get_db(db_path):
            await cog.list_links.callback(cog, ctx, filter="unread")

        ctx.send.assert_called_once()
        embed = ctx.send.call_args[1]["embed"]
        assert len(embed.fields) == 1
        assert "a.com" in embed.fields[0].value

    @pytest.mark.asyncio
    async def test_links_retrieves_read(self, cog, ctx, db_path):
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO links (url, title, tags, read) VALUES (?, ?, ?, ?)",
                ("https://a.com", "A", "", 0),
            )
            await db.execute(
                "INSERT INTO links (url, title, tags, read) VALUES (?, ?, ?, ?)",
                ("https://b.com", "B", "", 1),
            )
            await db.commit()

        with _patch_get_db(db_path):
            await cog.list_links.callback(cog, ctx, filter="read")

        ctx.send.assert_called_once()
        embed = ctx.send.call_args[1]["embed"]
        assert len(embed.fields) == 1
        assert "b.com" in embed.fields[0].value

    @pytest.mark.asyncio
    async def test_links_retrieves_all(self, cog, ctx, db_path):
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO links (url, title, tags, read) VALUES (?, ?, ?, ?)",
                ("https://a.com", "A", "", 0),
            )
            await db.execute(
                "INSERT INTO links (url, title, tags, read) VALUES (?, ?, ?, ?)",
                ("https://b.com", "B", "", 1),
            )
            await db.commit()

        with _patch_get_db(db_path):
            await cog.list_links.callback(cog, ctx, filter="all")

        ctx.send.assert_called_once()
        embed = ctx.send.call_args[1]["embed"]
        assert len(embed.fields) == 2


# ── read (mark as read) command ─────────────────────────────────────────────


class TestMarkRead:
    @pytest.mark.asyncio
    async def test_mark_read(self, cog, ctx, db_path):
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO links (url, title, tags) VALUES (?, ?, ?)",
                ("https://a.com", "A", ""),
            )
            await db.commit()

        with _patch_get_db(db_path):
            await cog.mark_read.callback(cog, ctx, link_id=1)

        ctx.send.assert_called_once_with("Link #1 marked as read.")

        async with aiosqlite.connect(db_path) as db:
            db.row_factory = _dict_factory
            cur = await db.execute("SELECT read FROM links WHERE id = 1")
            row = await cur.fetchone()
        assert row["read"] == 1

    @pytest.mark.asyncio
    async def test_nonexistent_id_returns_error(self, cog, ctx, db_path):
        with _patch_get_db(db_path):
            await cog.mark_read.callback(cog, ctx, link_id=999)

        ctx.send.assert_called_once_with("No link found with ID 999.")
