"""Tests for natural language command routing."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.claude_service import route_command


def _make_mock_response(text: str) -> MagicMock:
    """Create a mock Anthropic API response with the given text content."""
    mock_block = MagicMock()
    mock_block.text = text
    mock_message = MagicMock()
    mock_message.content = [mock_block]
    return mock_message


@pytest.mark.asyncio
@patch("services.claude_service.client")
async def test_route_command_add_todo(mock_client):
    """Test routing a message that should add a todo."""
    expected = {"action": "add_todo", "parameters": {"task": "buy groceries"}}
    mock_client.messages.create = AsyncMock(return_value=_make_mock_response(json.dumps(expected)))

    result = await route_command("add buy groceries to my todo list")

    assert result["action"] == "add_todo"
    assert result["parameters"]["task"] == "buy groceries"


@pytest.mark.asyncio
@patch("services.claude_service.client")
async def test_route_command_list_todos(mock_client):
    """Test routing a message that should list todos."""
    expected = {"action": "list_todos", "parameters": {"date": "today"}}
    mock_client.messages.create = AsyncMock(return_value=_make_mock_response(json.dumps(expected)))

    result = await route_command("what do I need to do today?")

    assert result["action"] == "list_todos"
    assert result["parameters"]["date"] == "today"


@pytest.mark.asyncio
@patch("services.claude_service.client")
async def test_route_command_general_chat(mock_client):
    """Test routing a general chat message."""
    expected = {
        "action": "general_chat",
        "parameters": {},
        "response": "Hey there! How can I help?",
    }
    mock_client.messages.create = AsyncMock(return_value=_make_mock_response(json.dumps(expected)))

    result = await route_command("hello!")

    assert result["action"] == "general_chat"
    assert "Hey there" in result["response"]


@pytest.mark.asyncio
@patch("services.claude_service.client")
async def test_route_command_save_link(mock_client):
    """Test routing a save link message."""
    expected = {
        "action": "save_link",
        "parameters": {"url": "https://example.com", "tags": "tech"},
    }
    mock_client.messages.create = AsyncMock(return_value=_make_mock_response(json.dumps(expected)))

    result = await route_command("save this link https://example.com tag it tech")

    assert result["action"] == "save_link"
    assert result["parameters"]["url"] == "https://example.com"
    assert result["parameters"]["tags"] == "tech"


@pytest.mark.asyncio
@patch("services.claude_service.client")
async def test_route_command_reflect(mock_client):
    """Test routing a reflect message."""
    expected = {"action": "reflect", "parameters": {}}
    mock_client.messages.create = AsyncMock(return_value=_make_mock_response(json.dumps(expected)))

    result = await route_command("how's my day going?")

    assert result["action"] == "reflect"


@pytest.mark.asyncio
@patch("services.claude_service.client")
async def test_route_command_set_reminder(mock_client):
    """Test routing a set reminder message."""
    expected = {
        "action": "set_reminder",
        "parameters": {"raw_input": "at 9pm call Sarah"},
    }
    mock_client.messages.create = AsyncMock(return_value=_make_mock_response(json.dumps(expected)))

    result = await route_command("remind me at 9pm to call Sarah")

    assert result["action"] == "set_reminder"
    assert result["parameters"]["raw_input"] == "at 9pm call Sarah"


@pytest.mark.asyncio
@patch("services.claude_service.client")
async def test_route_command_json_parse_error(mock_client):
    """Test that invalid JSON falls back to general_chat."""
    mock_client.messages.create = AsyncMock(
        return_value=_make_mock_response("Sorry, I didn't understand that.")
    )

    result = await route_command("asdfghjkl")

    assert result["action"] == "general_chat"
    assert result["response"] == "Sorry, I didn't understand that."
    assert result["parameters"] == {}


@pytest.mark.asyncio
@patch("services.claude_service.client")
async def test_route_command_sends_system_prompt(mock_client):
    """Test that route_command sends the proper system prompt."""
    expected = {"action": "general_chat", "parameters": {}, "response": "hi"}
    mock_client.messages.create = AsyncMock(return_value=_make_mock_response(json.dumps(expected)))

    await route_command("hello")

    call_kwargs = mock_client.messages.create.call_args
    assert call_kwargs.kwargs["system"] is not None
    assert "Available actions" in call_kwargs.kwargs["system"]
    assert "add_todo" in call_kwargs.kwargs["system"]
    assert call_kwargs.kwargs["model"] == "claude-haiku-4-5-20251001"
    assert call_kwargs.kwargs["max_tokens"] == 500


@pytest.mark.asyncio
@patch("services.claude_service.client")
async def test_route_command_check_email(mock_client):
    """Test routing a check email message."""
    expected = {"action": "check_email", "parameters": {}}
    mock_client.messages.create = AsyncMock(return_value=_make_mock_response(json.dumps(expected)))

    result = await route_command("any new emails?")

    assert result["action"] == "check_email"


@pytest.mark.asyncio
@patch("services.claude_service.client")
async def test_route_command_heading_out(mock_client):
    """Test routing a heading out context reminder."""
    expected = {
        "action": "check_context_reminders",
        "parameters": {"context": "heading_out"},
    }
    mock_client.messages.create = AsyncMock(return_value=_make_mock_response(json.dumps(expected)))

    result = await route_command("I'm heading out now")

    assert result["action"] == "check_context_reminders"
    assert result["parameters"]["context"] == "heading_out"
