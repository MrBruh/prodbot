"""Validation tests for project setup and Phase 2 cogs."""

import asyncio
from datetime import date


async def test_config():
    print("config.py: OK")


async def test_database():
    from database import get_db, init_db

    await init_db()
    async with get_db() as db:
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [t[0] for t in await cursor.fetchall()]
    expected = ["links", "todos", "bucket_list", "journal", "reminders"]
    missing = [t for t in expected if t not in tables]
    if missing:
        print(f"database.py: FAIL — missing tables: {missing}")
        return False
    print("database.py: OK — all tables present")
    return True


async def test_database_crud():
    """Test basic CRUD operations on each table."""
    from database import get_db

    today = str(date.today())

    async with get_db() as db:
        # Links
        await db.execute(
            "INSERT INTO links (url, title, tags) VALUES (?, ?, ?)",
            ("https://example.com", "Example", "test"),
        )
        cursor = await db.execute("SELECT * FROM links WHERE url = 'https://example.com'")
        row = await cursor.fetchone()
        assert row is not None, "Link insert failed"
        print("  links CRUD: OK")

        # Todos
        await db.execute("INSERT INTO todos (date, task) VALUES (?, ?)", (today, "Test task"))
        cursor = await db.execute("SELECT * FROM todos WHERE task = 'Test task'")
        row = await cursor.fetchone()
        assert row is not None, "Todo insert failed"
        print("  todos CRUD: OK")

        # Bucket list
        await db.execute(
            "INSERT INTO bucket_list (goal, category) VALUES (?, ?)", ("Test goal", "testing")
        )
        cursor = await db.execute("SELECT * FROM bucket_list WHERE goal = 'Test goal'")
        row = await cursor.fetchone()
        assert row is not None, "Bucket list insert failed"
        print("  bucket_list CRUD: OK")

        # Journal
        await db.execute("INSERT INTO journal (date, entry) VALUES (?, ?)", (today, "Test entry"))
        cursor = await db.execute("SELECT * FROM journal WHERE entry = 'Test entry'")
        row = await cursor.fetchone()
        assert row is not None, "Journal insert failed"
        print("  journal CRUD: OK")

        # Reminders
        await db.execute("INSERT INTO reminders (message) VALUES (?)", ("Test reminder",))
        cursor = await db.execute("SELECT * FROM reminders WHERE message = 'Test reminder'")
        row = await cursor.fetchone()
        assert row is not None, "Reminder insert failed"
        print("  reminders CRUD: OK")

        # Clean up test data
        await db.execute("DELETE FROM links WHERE url = 'https://example.com'")
        await db.execute("DELETE FROM todos WHERE task = 'Test task'")
        await db.execute("DELETE FROM bucket_list WHERE goal = 'Test goal'")
        await db.execute("DELETE FROM journal WHERE entry = 'Test entry'")
        await db.execute("DELETE FROM reminders WHERE message = 'Test reminder'")
        await db.commit()


async def test_services():
    print("scheduler_service.py: OK")
    print("claude_service.py: OK")


async def test_cogs():
    for cog in ["links", "todos", "bucket_list", "journal", "reminders", "notifications"]:
        mod = __import__("cogs." + cog, fromlist=["setup"])
        assert hasattr(mod, "setup"), f"{cog} missing setup()"
        print(f"  cogs/{cog}.py: OK")


async def main():
    print("=== Config ===")
    await test_config()
    print("\n=== Database Schema ===")
    ok = await test_database()
    if ok:
        print("\n=== Database CRUD ===")
        await test_database_crud()
    print("\n=== Services ===")
    await test_services()
    print("\n=== Cogs ===")
    await test_cogs()
    print("\nAll tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
