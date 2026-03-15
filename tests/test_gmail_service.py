"""Tests for the Gmail service."""

from unittest.mock import MagicMock, patch

import pytest

from services.gmail_service import get_unread_emails


@pytest.mark.asyncio
@patch("services.gmail_service._get_gmail_service")
async def test_get_unread_emails_not_configured(mock_get_service):
    """Test get_unread_emails when Gmail is not configured."""
    mock_get_service.return_value = None

    result = await get_unread_emails()

    assert result is None


@pytest.mark.asyncio
@patch("services.gmail_service._get_gmail_service")
async def test_get_unread_emails_no_messages(mock_get_service):
    """Test get_unread_emails with no unread messages."""
    mock_service = MagicMock()
    mock_get_service.return_value = mock_service

    # Mock the chained API calls
    mock_service.users().messages().list().execute.return_value = {"messages": []}

    result = await get_unread_emails()

    assert result == []


@pytest.mark.asyncio
@patch("services.gmail_service._get_gmail_service")
async def test_get_unread_emails_with_messages(mock_get_service):
    """Test get_unread_emails with unread messages."""
    mock_service = MagicMock()
    mock_get_service.return_value = mock_service

    # Mock list response
    mock_service.users().messages().list().execute.return_value = {
        "messages": [{"id": "msg1"}, {"id": "msg2"}]
    }

    # Mock get response for individual messages
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

    result = await get_unread_emails()

    assert result is not None
    assert len(result) == 2
    assert result[0]["from"] == "alice@example.com"
    assert result[0]["subject"] == "Hello World"
    assert result[1]["from"] == "bob@example.com"
    assert result[1]["subject"] == "Meeting Tomorrow"
