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
