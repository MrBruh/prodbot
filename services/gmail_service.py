import asyncio
import logging
from typing import Dict, List, Optional

from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
from database import get_db

logger = logging.getLogger(__name__)

# Least privilege: the metadata scope exposes labels and message headers
# (From/Subject) but never bodies or attachments. It also forbids the free-text
# `q` search parameter, so we list unread mail by the UNREAD label instead.
SCOPES = ["https://www.googleapis.com/auth/gmail.metadata"]
TOKEN_URI = "https://oauth2.googleapis.com/token"  # noqa: S105 (URL, not a secret)


def gmail_configured() -> bool:
    """True when the server has an OAuth client configured for Gmail."""
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


async def store_account(discord_user_id: int, email: Optional[str], refresh_token: str) -> None:
    """Insert or update the Gmail account linked to a Discord user."""
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO gmail_accounts (discord_user_id, email, refresh_token, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(discord_user_id) DO UPDATE SET
                email = excluded.email,
                refresh_token = excluded.refresh_token,
                updated_at = CURRENT_TIMESTAMP
            """,
            (discord_user_id, email, refresh_token),
        )
        await db.commit()


async def get_account(discord_user_id: int) -> Optional[Dict]:
    """Return the stored Gmail account for a Discord user, or None."""
    async with get_db() as db:
        db.row_factory = _dict_factory
        cursor = await db.execute(
            "SELECT discord_user_id, email, refresh_token FROM gmail_accounts "
            "WHERE discord_user_id = ?",
            (discord_user_id,),
        )
        return await cursor.fetchone()


async def delete_account(discord_user_id: int) -> bool:
    """Remove a user's stored Gmail account. Returns True if one was removed."""
    async with get_db() as db:
        cursor = await db.execute(
            "DELETE FROM gmail_accounts WHERE discord_user_id = ?",
            (discord_user_id,),
        )
        await db.commit()
        return cursor.rowcount > 0


def _service_for_account(account: Dict):
    """Build a Gmail API client from a stored refresh token. Blocking.

    The refresh token plus the app's client credentials are exchanged for a
    short-lived access token on each call, so nothing long-lived is held in
    memory beyond the refresh token already in the database.
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=account["refresh_token"],
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        token_uri=TOKEN_URI,
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


async def get_unread_emails(discord_user_id: int, max_results: int = 5) -> Optional[List[Dict]]:
    """Fetch a user's unread emails.

    Returns None if the user has not registered an account or the fetch fails
    (e.g. revoked/expired access); an empty list means the inbox is clear.
    """
    account = await get_account(discord_user_id)
    if not account:
        return None

    def _fetch():
        service = _service_for_account(account)
        results = (
            service.users()
            .messages()
            .list(userId="me", labelIds=["UNREAD"], maxResults=max_results)
            .execute()
        )
        messages = results.get("messages", [])

        emails = []
        for msg in messages:
            detail = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=msg["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject"],
                )
                .execute()
            )
            headers = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
            emails.append(
                {
                    "id": msg["id"],
                    "from": headers.get("From", "Unknown"),
                    "subject": headers.get("Subject", "(no subject)"),
                }
            )
        return emails

    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, _fetch)
    except Exception:
        logger.exception("Failed to fetch unread emails for user %s", discord_user_id)
        return None


def _dict_factory(cursor, row):
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}
