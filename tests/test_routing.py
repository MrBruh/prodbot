"""Tests for natural language command routing via Anthropic tool use."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.claude_service import TOOLS, route_command


def _make_mock_tool_response(name: str, tool_input: dict) -> MagicMock:
    """Create a mock Anthropic response containing a single tool_use block."""
    block = MagicMock()
    block.type = "tool_use"
    block.name = name
    block.input = tool_input
    message = MagicMock()
    message.content = [block]
    return message


def _make_mock_text_response(text: str) -> MagicMock:
    """Create a mock Anthropic response with only a text block (no tool_use)."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    message = MagicMock()
    message.content = [block]
    return message


@pytest.mark.asyncio
@patch("services.claude_service.client")
async def test_route_command_add_todo(mock_client):
    """A message that should add a todo routes to the add_todo tool."""
    mock_client.messages.create = AsyncMock(
        return_value=_make_mock_tool_response("add_todo", {"task": "buy groceries"})
    )

    result = await route_command("add buy groceries to my todo list")

    assert result["action"] == "add_todo"
    assert result["parameters"]["task"] == "buy groceries"


@pytest.mark.asyncio
@patch("services.claude_service.client")
async def test_route_command_list_todos(mock_client):
    """A message that should list todos routes to the list_todos tool."""
    mock_client.messages.create = AsyncMock(
        return_value=_make_mock_tool_response("list_todos", {"date": "today"})
    )

    result = await route_command("what do I need to do today?")

    assert result["action"] == "list_todos"
    assert result["parameters"]["date"] == "today"


@pytest.mark.asyncio
@patch("services.claude_service.client")
async def test_route_command_general_chat(mock_client):
    """general_chat lifts its reply out of the tool input to the top level."""
    mock_client.messages.create = AsyncMock(
        return_value=_make_mock_tool_response(
            "general_chat", {"response": "Hey there! How can I help?"}
        )
    )

    result = await route_command("hello!")

    assert result["action"] == "general_chat"
    assert "Hey there" in result["response"]
    # response is lifted out of parameters, matching the original contract
    assert result["parameters"] == {}


@pytest.mark.asyncio
@patch("services.claude_service.client")
async def test_route_command_save_link(mock_client):
    """A save-link message routes to the save_link tool with url and tags."""
    mock_client.messages.create = AsyncMock(
        return_value=_make_mock_tool_response(
            "save_link", {"url": "https://example.com", "tags": "tech"}
        )
    )

    result = await route_command("save this link https://example.com tag it tech")

    assert result["action"] == "save_link"
    assert result["parameters"]["url"] == "https://example.com"
    assert result["parameters"]["tags"] == "tech"


@pytest.mark.asyncio
@patch("services.claude_service.client")
async def test_route_command_reflect(mock_client):
    """A reflect message routes to the reflect tool."""
    mock_client.messages.create = AsyncMock(return_value=_make_mock_tool_response("reflect", {}))

    result = await route_command("how's my day going?")

    assert result["action"] == "reflect"
    assert result["parameters"] == {}


@pytest.mark.asyncio
@patch("services.claude_service.client")
async def test_route_command_set_reminder_timed(mock_client):
    """A timed set-reminder message routes to set_reminder with a structured remind_at."""
    mock_client.messages.create = AsyncMock(
        return_value=_make_mock_tool_response(
            "set_reminder", {"message": "call Sarah", "remind_at": "2026-06-30T21:00:00"}
        )
    )

    result = await route_command("remind me at 9pm to call Sarah")

    assert result["action"] == "set_reminder"
    assert result["parameters"]["message"] == "call Sarah"
    assert result["parameters"]["remind_at"] == "2026-06-30T21:00:00"


@pytest.mark.asyncio
@patch("services.claude_service.client")
async def test_route_command_set_reminder_context(mock_client):
    """A context set-reminder message routes to set_reminder with a context."""
    mock_client.messages.create = AsyncMock(
        return_value=_make_mock_tool_response(
            "set_reminder", {"message": "grab keys", "context": "heading_out"}
        )
    )

    result = await route_command("remind me to grab keys before I leave")

    assert result["action"] == "set_reminder"
    assert result["parameters"]["message"] == "grab keys"
    assert result["parameters"]["context"] == "heading_out"


@pytest.mark.asyncio
@patch("services.claude_service.client")
async def test_route_command_no_tool_use_falls_back(mock_client):
    """A response with no tool_use block falls back to general_chat (API failure)."""
    mock_client.messages.create = AsyncMock(
        return_value=_make_mock_text_response("Sorry, I didn't understand that.")
    )

    result = await route_command("asdfghjkl")

    assert result["action"] == "general_chat"
    assert result["response"] == "Sorry, I didn't understand that."
    assert result["parameters"] == {}


@pytest.mark.asyncio
@patch("services.claude_service.client")
async def test_route_command_sends_tools_and_tool_choice(mock_client):
    """route_command forces a single tool call against the action tool list."""
    mock_client.messages.create = AsyncMock(
        return_value=_make_mock_tool_response("general_chat", {"response": "hi"})
    )

    await route_command("hello")

    kwargs = mock_client.messages.create.call_args.kwargs

    # Tools are passed, and cover the action surface
    tool_names = [t["name"] for t in kwargs["tools"]]
    assert "add_todo" in tool_names
    assert "set_reminder" in tool_names
    assert "general_chat" in tool_names

    # A tool call is forced, and only one tool may be called
    assert kwargs["tool_choice"] == {"type": "any", "disable_parallel_tool_use": True}

    assert kwargs["model"] == "claude-haiku-4-5-20251001"
    assert kwargs["max_tokens"] == 500
    assert kwargs["system"]


@pytest.mark.asyncio
@patch("services.claude_service.client")
async def test_route_command_check_email(mock_client):
    """A check-email message routes to the check_email tool."""
    mock_client.messages.create = AsyncMock(
        return_value=_make_mock_tool_response("check_email", {})
    )

    result = await route_command("any new emails?")

    assert result["action"] == "check_email"


@pytest.mark.asyncio
@patch("services.claude_service.client")
async def test_route_command_heading_out(mock_client):
    """A heading-out message routes to check_context_reminders with heading_out."""
    mock_client.messages.create = AsyncMock(
        return_value=_make_mock_tool_response("check_context_reminders", {"context": "heading_out"})
    )

    result = await route_command("I'm heading out now")

    assert result["action"] == "check_context_reminders"
    assert result["parameters"]["context"] == "heading_out"


def test_check_context_tool_restricts_to_heading_out():
    """The context schema only blesses heading_out — the one wired dispatch path."""
    tool = next(t for t in TOOLS if t["name"] == "check_context_reminders")
    assert tool["input_schema"]["properties"]["context"]["enum"] == ["heading_out"]


def test_general_chat_tool_requires_response():
    """general_chat must require a response so the bot never emits an empty reply."""
    tool = next(t for t in TOOLS if t["name"] == "general_chat")
    assert "response" in tool["input_schema"]["required"]


def test_set_reminder_tool_is_structured():
    """set_reminder emits structured fields (no raw_input) so the NL path skips a 2nd LLM call."""
    tool = next(t for t in TOOLS if t["name"] == "set_reminder")
    props = tool["input_schema"]["properties"]
    assert set(props) == {"message", "remind_at", "context"}
    assert "raw_input" not in props
    assert tool["input_schema"]["required"] == ["message"]
    assert props["context"]["enum"] == ["heading_out", "morning", "evening"]
