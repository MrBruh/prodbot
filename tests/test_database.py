"""Unit tests for database CRUD operations on all tables."""

import os
import tempfile
import pytest
import pytest_asyncio
import aiosqlite

# We import init_db and patch DB_PATH so it uses a temp file.
import database


@pytest_asyncio.fixture
async def db_path(tmp_path):
    """Create a temporary database file and initialise the schema."""
    path = str(tmp_path / "test.db")
    original = database.DB_PATH
    database.DB_PATH = path
    await database.init_db()
    yield path
    database.DB_PATH = original


# ── helper ──────────────────────────────────────────────────────────────────


def _dict_factory(cursor, row):
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


# ── _dict_factory tests ────────────────────────────────────────────────────


class TestDictFactory:
    def test_converts_row_to_dict(self):
        """_dict_factory should turn (cursor.description, row) into a dict."""

        class FakeCursor:
            description = [("id",), ("name",), ("value",)]

        result = _dict_factory(FakeCursor(), (1, "test", 42))
        assert result == {"id": 1, "name": "test", "value": 42}

    def test_empty_row(self):
        class FakeCursor:
            description = []

        result = _dict_factory(FakeCursor(), ())
        assert result == {}


# ── links table ─────────────────────────────────────────────────────────────


class TestLinksTable:
    @pytest.mark.asyncio
    async def test_insert_and_select(self, db_path):
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO links (url, title, tags) VALUES (?, ?, ?)",
                ("https://example.com", "Example", "test"),
            )
            await db.commit()
            db.row_factory = _dict_factory
            cur = await db.execute("SELECT * FROM links WHERE id = 1")
            row = await cur.fetchone()

        assert row["url"] == "https://example.com"
        assert row["title"] == "Example"
        assert row["tags"] == "test"
        assert row["read"] == 0

    @pytest.mark.asyncio
    async def test_update_read_status(self, db_path):
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO links (url, title, tags) VALUES (?, ?, ?)",
                ("https://example.com", "Ex", ""),
            )
            await db.commit()
            await db.execute("UPDATE links SET read = 1 WHERE id = 1")
            await db.commit()
            db.row_factory = _dict_factory
            cur = await db.execute("SELECT read FROM links WHERE id = 1")
            row = await cur.fetchone()

        assert row["read"] == 1

    @pytest.mark.asyncio
    async def test_delete(self, db_path):
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO links (url, title, tags) VALUES (?, ?, ?)",
                ("https://example.com", "Ex", ""),
            )
            await db.commit()
            await db.execute("DELETE FROM links WHERE id = 1")
            await db.commit()
            cur = await db.execute("SELECT COUNT(*) FROM links")
            count = (await cur.fetchone())[0]

        assert count == 0


# ── todos table ─────────────────────────────────────────────────────────────


class TestTodosTable:
    @pytest.mark.asyncio
    async def test_insert_and_select(self, db_path):
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO todos (date, task) VALUES (?, ?)",
                ("2025-03-20", "Write tests"),
            )
            await db.commit()
            db.row_factory = _dict_factory
            cur = await db.execute("SELECT * FROM todos WHERE id = 1")
            row = await cur.fetchone()

        assert row["date"] == "2025-03-20"
        assert row["task"] == "Write tests"
        assert row["completed"] == 0

    @pytest.mark.asyncio
    async def test_update_completed(self, db_path):
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO todos (date, task) VALUES (?, ?)",
                ("2025-03-20", "Task"),
            )
            await db.commit()
            await db.execute("UPDATE todos SET completed = 1 WHERE id = 1")
            await db.commit()
            db.row_factory = _dict_factory
            cur = await db.execute("SELECT completed FROM todos WHERE id = 1")
            row = await cur.fetchone()

        assert row["completed"] == 1

    @pytest.mark.asyncio
    async def test_delete(self, db_path):
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO todos (date, task) VALUES (?, ?)",
                ("2025-03-20", "Task"),
            )
            await db.commit()
            await db.execute("DELETE FROM todos WHERE id = 1")
            await db.commit()
            cur = await db.execute("SELECT COUNT(*) FROM todos")
            count = (await cur.fetchone())[0]

        assert count == 0


# ── bucket_list table ───────────────────────────────────────────────────────


class TestBucketListTable:
    @pytest.mark.asyncio
    async def test_insert_and_select(self, db_path):
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO bucket_list (goal, category) VALUES (?, ?)",
                ("Learn Rust", "learning"),
            )
            await db.commit()
            db.row_factory = _dict_factory
            cur = await db.execute("SELECT * FROM bucket_list WHERE id = 1")
            row = await cur.fetchone()

        assert row["goal"] == "Learn Rust"
        assert row["category"] == "learning"
        assert row["status"] == "not_started"
        assert row["completed_at"] is None

    @pytest.mark.asyncio
    async def test_update_status(self, db_path):
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO bucket_list (goal, category) VALUES (?, ?)",
                ("Goal", "general"),
            )
            await db.commit()
            await db.execute(
                "UPDATE bucket_list SET status = 'in_progress' WHERE id = 1"
            )
            await db.commit()
            db.row_factory = _dict_factory
            cur = await db.execute("SELECT status FROM bucket_list WHERE id = 1")
            row = await cur.fetchone()

        assert row["status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_delete(self, db_path):
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO bucket_list (goal, category) VALUES (?, ?)",
                ("Goal", "general"),
            )
            await db.commit()
            await db.execute("DELETE FROM bucket_list WHERE id = 1")
            await db.commit()
            cur = await db.execute("SELECT COUNT(*) FROM bucket_list")
            count = (await cur.fetchone())[0]

        assert count == 0


# ── journal table ───────────────────────────────────────────────────────────


class TestJournalTable:
    @pytest.mark.asyncio
    async def test_insert_and_select(self, db_path):
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO journal (date, entry) VALUES (?, ?)",
                ("2025-03-20", "Felt productive today"),
            )
            await db.commit()
            db.row_factory = _dict_factory
            cur = await db.execute("SELECT * FROM journal WHERE id = 1")
            row = await cur.fetchone()

        assert row["date"] == "2025-03-20"
        assert row["entry"] == "Felt productive today"
        assert row["mood"] is None

    @pytest.mark.asyncio
    async def test_update_mood(self, db_path):
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO journal (date, entry) VALUES (?, ?)",
                ("2025-03-20", "Entry"),
            )
            await db.commit()
            await db.execute("UPDATE journal SET mood = 'happy' WHERE id = 1")
            await db.commit()
            db.row_factory = _dict_factory
            cur = await db.execute("SELECT mood FROM journal WHERE id = 1")
            row = await cur.fetchone()

        assert row["mood"] == "happy"

    @pytest.mark.asyncio
    async def test_delete(self, db_path):
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO journal (date, entry) VALUES (?, ?)",
                ("2025-03-20", "Entry"),
            )
            await db.commit()
            await db.execute("DELETE FROM journal WHERE id = 1")
            await db.commit()
            cur = await db.execute("SELECT COUNT(*) FROM journal")
            count = (await cur.fetchone())[0]

        assert count == 0


# ── reminders table ─────────────────────────────────────────────────────────


class TestRemindersTable:
    @pytest.mark.asyncio
    async def test_insert_and_select(self, db_path):
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO reminders (message, remind_at, context, recurring) VALUES (?, ?, ?, ?)",
                ("Take break", "2025-03-20T15:00:00", "health", 0),
            )
            await db.commit()
            db.row_factory = _dict_factory
            cur = await db.execute("SELECT * FROM reminders WHERE id = 1")
            row = await cur.fetchone()

        assert row["message"] == "Take break"
        assert row["remind_at"] == "2025-03-20T15:00:00"
        assert row["context"] == "health"
        assert row["recurring"] == 0
        assert row["fired"] == 0

    @pytest.mark.asyncio
    async def test_update_fired(self, db_path):
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO reminders (message) VALUES (?)", ("Reminder",)
            )
            await db.commit()
            await db.execute("UPDATE reminders SET fired = 1 WHERE id = 1")
            await db.commit()
            db.row_factory = _dict_factory
            cur = await db.execute("SELECT fired FROM reminders WHERE id = 1")
            row = await cur.fetchone()

        assert row["fired"] == 1

    @pytest.mark.asyncio
    async def test_delete(self, db_path):
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO reminders (message) VALUES (?)", ("Reminder",)
            )
            await db.commit()
            await db.execute("DELETE FROM reminders WHERE id = 1")
            await db.commit()
            cur = await db.execute("SELECT COUNT(*) FROM reminders")
            count = (await cur.fetchone())[0]

        assert count == 0
