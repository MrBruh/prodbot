# Discord Life Bot - Improvement Plan

This document outlines recommended changes to reduce technical debt and improve project maintainability.

---

## Phase 1: Critical Fixes

### 1.1 Fix Sync API Blocking Event Loop
**File:** `services/claude_service.py`

**Problem:** Using synchronous Anthropic client in async functions blocks the entire bot during API calls.

**Solution:**
```python
# Change from:
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# To:
client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

# Then use await:
message = await client.messages.create(...)
```

**Lines to change:** 4, 9-18, 39-44

---

### 1.2 Add Proper Exception Handling
**File:** `cogs/links.py`

**Problem:** Bare `except Exception:` silently swallows all errors at line 16.

**Solution:**
```python
import logging
logger = logging.getLogger(__name__)

# Replace:
except Exception:
    title = None

# With:
except anthropic.APIError as e:
    logger.warning(f"Failed to summarize URL: {e}")
    title = None
```

---

### 1.3 Add Environment Variable Validation
**File:** `config.py`

**Problem:** No validation - bot crashes with cryptic errors if `.env` is missing or incomplete.

**Solution:**
```python
import os
import sys
from dotenv import load_dotenv

load_dotenv()

def _get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        print(f"ERROR: Required environment variable {name} is not set")
        sys.exit(1)
    return value

DISCORD_TOKEN: str = _get_required_env("DISCORD_TOKEN")
ANTHROPIC_API_KEY: str = _get_required_env("ANTHROPIC_API_KEY")
BOT_CHANNEL_ID: int = int(_get_required_env("BOT_CHANNEL_ID"))
```

---

## Phase 2: Code Quality

### 2.1 Create pyproject.toml
**New file:** `pyproject.toml`

Create modern Python project configuration with:
- Project metadata
- Ruff linter configuration
- Pytest configuration
- Dependency groups (runtime vs dev)

**Template:**
```toml
[project]
name = "discord-life-bot"
version = "0.1.0"
requires-python = ">=3.10"

[tool.ruff]
line-length = 100
select = ["E", "F", "W", "I", "N", "UP", "B", "C4"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff.format]
quote-style = "double"
```

---

### 2.2 Consolidate _dict_factory Function
**Files:** `cogs/links.py`, `cogs/todos.py`, `cogs/journal.py`, `cogs/bucket_list.py`

**Problem:** Identical function duplicated in 4 files.

**Solution:**
1. Move to `database.py`:
```python
def dict_factory(cursor, row):
    """Convert database row to dictionary."""
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}
```

2. Update all cog files to import:
```python
from database import dict_factory
```

3. Remove local `_dict_factory` from each cog (lines 79-80 in links.py, 81-82 in todos.py, 84-85 in journal.py, 99-100 in bucket_list.py)

---

### 2.3 Create Shared Test Fixtures
**New file:** `tests/conftest.py`

**Problem:** Identical fixtures duplicated across all test files.

**Solution:** Create `conftest.py` with shared fixtures:
```python
import pytest
import aiosqlite
from unittest.mock import AsyncMock, MagicMock
import tempfile
import os

@pytest.fixture
async def db_path():
    """Create temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)

@pytest.fixture
async def db(db_path):
    """Create and initialize test database."""
    async with aiosqlite.connect(db_path) as db:
        # Run schema initialization from database.py
        await db.executescript(SCHEMA)
        await db.commit()
        yield db

@pytest.fixture
def bot():
    """Create mock bot."""
    return MagicMock()

@pytest.fixture
def ctx(bot):
    """Create mock context."""
    ctx = MagicMock()
    ctx.send = AsyncMock()
    ctx.bot = bot
    return ctx
```

Then remove duplicated fixtures from individual test files.

---

### 2.4 Replace print() with Logging
**Files:** `bot.py`, `test_setup.py`

**Problem:** Using `print()` instead of proper logging.

**Solution for bot.py:**
```python
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

# Replace:
print(f"Logged in as {bot.user}")

# With:
logger.info(f"Logged in as {bot.user}")
```

---

### 2.5 Move Hardcoded Values to Config
**Files:** Multiple

| Value | Current Location | Move To |
|-------|-----------------|---------|
| `"bot.db"` | `database.py:3` | `config.py` |
| `"sqlite:///jobs.db"` | `scheduler_service.py:5` | `config.py` |
| `"claude-haiku-4-5-20251001"` | `claude_service.py:10` | `config.py` |
| `"claude-sonnet-4-6"` | `claude_service.py:40` | `config.py` |
| `max_tokens=100/300` | `claude_service.py` | `config.py` |
| `command_prefix="!"` | `bot.py:10` | `config.py` |
| `links[:15]` | `cogs/links.py:55` | `config.py` |

**Add to config.py:**
```python
# Database
DATABASE_PATH = os.getenv("DATABASE_PATH", "bot.db")
JOBS_DATABASE_PATH = os.getenv("JOBS_DATABASE_PATH", "sqlite:///jobs.db")

# Claude API
CLAUDE_HAIKU_MODEL = os.getenv("CLAUDE_HAIKU_MODEL", "claude-haiku-4-5-20251001")
CLAUDE_SONNET_MODEL = os.getenv("CLAUDE_SONNET_MODEL", "claude-sonnet-4-6")
CLAUDE_MAX_TOKENS_SUMMARY = int(os.getenv("CLAUDE_MAX_TOKENS_SUMMARY", "100"))
CLAUDE_MAX_TOKENS_REFLECT = int(os.getenv("CLAUDE_MAX_TOKENS_REFLECT", "300"))

# Bot Settings
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")
LINKS_PAGE_SIZE = int(os.getenv("LINKS_PAGE_SIZE", "15"))
```

---

## Phase 3: Project Infrastructure

### 3.1 Create README.md
**New file:** `README.md`

Include:
- Project description
- Features list
- Requirements (Python 3.10+)
- Setup instructions
- Environment variables reference
- Running the bot
- Running tests
- Project structure

---

### 3.2 Create .env.example
**New file:** `.env.example`

```
# Discord Configuration
DISCORD_TOKEN=your_discord_bot_token_here
BOT_CHANNEL_ID=123456789

# Anthropic API
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Optional - Database paths (defaults shown)
# DATABASE_PATH=bot.db
# JOBS_DATABASE_PATH=sqlite:///jobs.db

# Optional - Claude models (defaults shown)
# CLAUDE_HAIKU_MODEL=claude-haiku-4-5-20251001
# CLAUDE_SONNET_MODEL=claude-sonnet-4-6

# Optional - Bot settings
# COMMAND_PREFIX=!
# LINKS_PAGE_SIZE=15
```

---

### 3.3 Add GitHub Actions CI
**New file:** `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: |
          pip install ruff
      - name: Lint with ruff
        run: ruff check .

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      - name: Run tests
        run: pytest tests/ -v
```

---

### 3.4 Pin Dependency Versions
**File:** `requirements.txt`

**Problem:** No version pinning leads to dependency drift.

**Solution:** Pin versions with compatible release operator:
```
discord.py~=2.3
anthropic~=0.18
aiosqlite~=0.19
apscheduler~=3.10
sqlalchemy~=2.0
python-dotenv~=1.0
google-api-python-client~=2.100
google-auth-httplib2~=0.2
google-auth-oauthlib~=1.2
pytest~=8.0
pytest-asyncio~=0.23
```

Or create separate files:
- `requirements.txt` - runtime dependencies
- `requirements-dev.txt` - dev dependencies (pytest, ruff)

---

### 3.5 Improve .gitignore
**File:** `.gitignore`

Add missing patterns:
```gitignore
# Secrets (existing)
private-keys.json
.env

# Python (expand)
venv/
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
*.so
*.egg-info/
dist/
build/

# Testing
.pytest_cache/
.coverage
htmlcov/

# Type checking
.mypy_cache/

# IDEs
.idea/
.vscode/
*.swp
*.swo

# Logs
*.log

# Databases (existing)
bot.db
jobs.db
token.json
credentials.json
```

---

## Phase 4: Polish

### 4.1 Add Input Validation
**Files:** All cog files

**Add validation for:**
- URL format in `links.py`
- Max length for tasks, journal entries, goals
- Valid date formats

**Example for links.py:**
```python
from urllib.parse import urlparse

def is_valid_url(url: str) -> bool:
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

# In save command:
if not is_valid_url(url):
    await ctx.send("Invalid URL format.")
    return
```

**Example max length validation:**
```python
MAX_TASK_LENGTH = 200
MAX_JOURNAL_LENGTH = 2000
MAX_GOAL_LENGTH = 500
```

---

### 4.2 Add Command Cooldowns
**Files:** All cog files

**Problem:** No rate limiting, vulnerable to spam.

**Solution:**
```python
from discord.ext import commands

@commands.cooldown(1, 5, commands.BucketType.user)  # 1 use per 5 seconds per user
@todo_group.command(name="add")
async def add(self, ctx, *, task: str):
    ...
```

---

### 4.3 Handle Stub Cogs
**Files:** `cogs/reminders.py`, `cogs/notifications.py`

**Options:**
1. Implement the features
2. Remove the stubs from the codebase
3. Add `@commands.command(enabled=False)` and document as "coming soon"

**Recommendation:** Remove from `bot.py` loading until implemented.

---

### 4.4 Add Database Error Handling
**Files:** All cog files

**Problem:** Database errors will crash the bot.

**Solution:** Wrap database operations:
```python
try:
    async with get_db() as db:
        await db.execute(...)
        await db.commit()
except aiosqlite.Error as e:
    logger.error(f"Database error: {e}")
    await ctx.send("An error occurred. Please try again.")
    return
```

---

### 4.5 Create Dockerfile (Optional)
**New file:** `Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
```

---

## Implementation Order

1. **Week 1:** Phase 1 (Critical Fixes) - Items 1.1, 1.2, 1.3
2. **Week 2:** Phase 2 (Code Quality) - Items 2.1, 2.2, 2.3, 2.4, 2.5
3. **Week 3:** Phase 3 (Infrastructure) - Items 3.1, 3.2, 3.3, 3.4, 3.5
4. **Week 4:** Phase 4 (Polish) - Items 4.1, 4.2, 4.3, 4.4

---

## Estimated Effort

| Phase | Effort | Impact |
|-------|--------|--------|
| Phase 1 | 2-3 hours | Critical stability |
| Phase 2 | 4-6 hours | Long-term maintainability |
| Phase 3 | 2-3 hours | Project professionalism |
| Phase 4 | 3-4 hours | Robustness & UX |

**Total:** 11-16 hours
