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
BOT_CHANNEL_NAME: str = os.getenv("BOT_CHANNEL_NAME", "prodbot")

# Zone for interpreting reminder times, so "2pm" means 2pm here regardless of
# the server's system clock zone. Any IANA name, e.g. "America/New_York".
TIMEZONE: str = os.getenv("TIMEZONE", "America/New_York")
