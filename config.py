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

# --- Gmail OAuth (optional) --------------------------------------------------
# When these are set, members can self-register their own Gmail via
# `!email register` (see deploy/GMAIL_SETUP.md). Left empty, all email features
# report "not set up" and the OAuth callback server is not started.
GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
OAUTH_REDIRECT_URI: str = os.getenv("OAUTH_REDIRECT_URI", "")
OAUTH_SERVER_HOST: str = os.getenv("OAUTH_SERVER_HOST", "127.0.0.1")
OAUTH_SERVER_PORT: int = int(os.getenv("OAUTH_SERVER_PORT", "8080"))
