import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Gmail API scopes
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def _get_gmail_service():
    """Build and return a Gmail API service object, or None if not configured."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        logger.warning("Google API libraries not installed")
        return None

    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif os.path.exists("credentials.json"):
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
            with open("token.json", "w") as token:
                token.write(creds.to_json())
        else:
            logger.info("Gmail not configured — credentials.json not found")
            return None

    return build("gmail", "v1", credentials=creds)


async def get_unread_emails(max_results: int = 5) -> Optional[List[Dict]]:
    """Fetch unread emails from Gmail. Returns None if Gmail is not configured."""
    import asyncio

    service = _get_gmail_service()
    if not service:
        return None

    def _fetch():
        results = (
            service.users()
            .messages()
            .list(userId="me", q="is:unread", maxResults=max_results)
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
    return await loop.run_in_executor(None, _fetch)
