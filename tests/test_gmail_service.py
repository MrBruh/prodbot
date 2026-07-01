"""Tests for the per-user Gmail service."""

from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio

import database
from services.gmail_service import (
    delete_account,
    get_account,
    get_unread_emails,
    gmail_configured,
    store_account,
)


@pytest_asyncio.fixture
async def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    original = database.DB_PATH
    database.DB_PATH = path
    await database.init_db()
    yield path
    database.DB_PATH = original


# --- gmail_configured --------------------------------------------------------


@patch("services.gmail_service.GOOGLE_CLIENT_SECRET", "secret")
@patch("services.gmail_service.GOOGLE_CLIENT_ID", "id")
def test_gmail_configured_true():
    assert gmail_configured() is True


@patch("services.gmail_service.GOOGLE_CLIENT_SECRET", "")
@patch("services.gmail_service.GOOGLE_CLIENT_ID", "")
def test_gmail_configured_false_when_missing():
    assert gmail_configured() is False


# --- account storage ---------------------------------------------------------


@pytest.mark.asyncio
async def test_store_and_get_account(db_path):
    await store_account(42, "me@example.com", "refresh-1")

    account = await get_account(42)
    assert account is not None
    assert account["discord_user_id"] == 42
    assert account["email"] == "me@example.com"
    assert account["refresh_token"] == "refresh-1"


@pytest.mark.asyncio
async def test_store_account_upserts(db_path):
    await store_account(42, "me@example.com", "refresh-1")
    await store_account(42, "me@example.com", "refresh-2")

    account = await get_account(42)
    assert account["refresh_token"] == "refresh-2"


@pytest.mark.asyncio
async def test_get_account_missing_returns_none(db_path):
    assert await get_account(999) is None


@pytest.mark.asyncio
async def test_delete_account(db_path):
    await store_account(42, "me@example.com", "refresh-1")

    assert await delete_account(42) is True
    assert await get_account(42) is None
    # Deleting again reports nothing removed.
    assert await delete_account(42) is False


# --- get_unread_emails -------------------------------------------------------


@pytest.mark.asyncio
@patch("services.gmail_service.get_account")
async def test_get_unread_emails_not_registered(mock_get_account):
    mock_get_account.return_value = None

    assert await get_unread_emails(42) is None


@pytest.mark.asyncio
@patch("services.gmail_service._service_for_account")
@patch("services.gmail_service.get_account")
async def test_get_unread_emails_no_messages(mock_get_account, mock_service_for):
    mock_get_account.return_value = {"refresh_token": "r", "email": "me@example.com"}
    mock_service = MagicMock()
    mock_service_for.return_value = mock_service
    mock_service.users().messages().list().execute.return_value = {"messages": []}

    assert await get_unread_emails(42) == []


@pytest.mark.asyncio
@patch("services.gmail_service._service_for_account")
@patch("services.gmail_service.get_account")
async def test_get_unread_emails_with_messages(mock_get_account, mock_service_for):
    mock_get_account.return_value = {"refresh_token": "r", "email": "me@example.com"}
    mock_service = MagicMock()
    mock_service_for.return_value = mock_service

    mock_service.users().messages().list().execute.return_value = {
        "messages": [{"id": "msg1"}, {"id": "msg2"}]
    }
    mock_service.users().messages().get().execute.side_effect = [
        {
            "payload": {
                "headers": [
                    {"name": "From", "value": "alice@example.com"},
                    {"name": "Subject", "value": "Hello World"},
                ]
            }
        },
        {
            "payload": {
                "headers": [
                    {"name": "From", "value": "bob@example.com"},
                    {"name": "Subject", "value": "Meeting Tomorrow"},
                ]
            }
        },
    ]

    result = await get_unread_emails(42)

    assert result is not None
    assert len(result) == 2
    assert result[0]["from"] == "alice@example.com"
    assert result[0]["subject"] == "Hello World"
    assert result[1]["from"] == "bob@example.com"


@pytest.mark.asyncio
@patch("services.gmail_service._service_for_account")
@patch("services.gmail_service.get_account")
async def test_get_unread_emails_swallows_errors(mock_get_account, mock_service_for):
    mock_get_account.return_value = {"refresh_token": "r", "email": "me@example.com"}
    mock_service_for.side_effect = RuntimeError("token revoked")

    assert await get_unread_emails(42) is None
