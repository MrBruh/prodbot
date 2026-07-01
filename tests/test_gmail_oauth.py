"""Tests for the Gmail OAuth consent flow and callback server."""

from unittest.mock import MagicMock, patch

import pytest

from services import gmail_oauth
from services.gmail_oauth import create_pending, pop_pending, start_oauth_server


@pytest.fixture(autouse=True)
def clear_pending():
    gmail_oauth._PENDING.clear()
    yield
    gmail_oauth._PENDING.clear()


@patch("services.gmail_oauth.OAUTH_REDIRECT_URI", "https://prodbot.example.com/oauth/callback")
@patch("services.gmail_oauth.GOOGLE_CLIENT_SECRET", "secret")
@patch("services.gmail_oauth.GOOGLE_CLIENT_ID", "client-id.apps.googleusercontent.com")
def test_create_pending_returns_consent_url():
    url = create_pending(42)

    assert "accounts.google.com" in url
    assert "client-id.apps.googleusercontent.com" in url
    assert len(gmail_oauth._PENDING) == 1


@patch("services.gmail_oauth.OAUTH_REDIRECT_URI", "https://prodbot.example.com/oauth/callback")
@patch("services.gmail_oauth.GOOGLE_CLIENT_SECRET", "secret")
@patch("services.gmail_oauth.GOOGLE_CLIENT_ID", "client-id")
def test_pop_pending_is_one_shot():
    create_pending(42)
    state = next(iter(gmail_oauth._PENDING))

    assert pop_pending(state) == 42
    # A second use of the same state fails — the token is consumed.
    assert pop_pending(state) is None


def test_pop_pending_unknown_state():
    assert pop_pending("does-not-exist") is None


@patch("services.gmail_oauth.OAUTH_REDIRECT_URI", "https://prodbot.example.com/oauth/callback")
@patch("services.gmail_oauth.GOOGLE_CLIENT_SECRET", "secret")
@patch("services.gmail_oauth.GOOGLE_CLIENT_ID", "client-id")
def test_pop_pending_expired():
    with patch("services.gmail_oauth.time.monotonic", return_value=1000.0):
        create_pending(42)
    state = next(iter(gmail_oauth._PENDING))

    # Jump past the TTL — the pending state should be treated as expired.
    with patch("services.gmail_oauth.time.monotonic", return_value=1000.0 + 10_000):
        assert pop_pending(state) is None


@pytest.mark.asyncio
@patch("services.gmail_oauth.gmail_configured", return_value=False)
async def test_start_oauth_server_skips_when_unconfigured(_cfg):
    runner = await start_oauth_server(MagicMock())

    assert runner is None
