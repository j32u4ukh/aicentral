from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel, Field

from aicentral import complete_structured
from aicentral.core.errors import StructuredOutputError


class Ticket(BaseModel):
    title: str
    priority: int = Field(ge=1, le=5)


def _raw_with_args(arguments: str) -> dict:
    return {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {"function": {"name": "ticket", "arguments": arguments}}
                    ],
                }
            }
        ]
    }


@patch("aicentral.core.client.get_provider_module")
def test_complete_structured_success(mock_get_provider: MagicMock) -> None:
    provider = MagicMock()
    provider.chat_completions_raw.return_value = _raw_with_args(
        '{"title": "伺服器當機", "priority": 4}'
    )
    mock_get_provider.return_value = provider

    ticket = complete_structured(
        messages=[{"role": "user", "content": "很急"}],
        response_model=Ticket,
        model="ollama/gemma4:e2b",
    )

    assert isinstance(ticket, Ticket)
    assert ticket.title == "伺服器當機"
    assert ticket.priority == 4
    call_kwargs = provider.chat_completions_raw.call_args.kwargs
    assert "tools" in call_kwargs
    assert call_kwargs["tool_choice"] == {
        "type": "function",
        "function": {"name": "ticket"},
    }


@patch("aicentral.core.client.get_provider_module")
def test_complete_structured_retries_then_succeeds(mock_get_provider: MagicMock) -> None:
    provider = MagicMock()
    provider.chat_completions_raw.side_effect = [
        _raw_with_args('{"title": "x", "priority": 99}'),
        _raw_with_args('{"title": "ok", "priority": 2}'),
    ]
    mock_get_provider.return_value = provider

    ticket = complete_structured(
        messages=[{"role": "user", "content": "test"}],
        response_model=Ticket,
        max_retries=1,
    )
    assert ticket.priority == 2
    assert provider.chat_completions_raw.call_count == 2


@patch("aicentral.core.client.get_provider_module")
def test_complete_structured_exhausted_raises(mock_get_provider: MagicMock) -> None:
    provider = MagicMock()
    provider.chat_completions_raw.return_value = _raw_with_args(
        '{"title": "x", "priority": 99}'
    )
    mock_get_provider.return_value = provider

    with pytest.raises(StructuredOutputError) as exc_info:
        complete_structured(
            messages=[{"role": "user", "content": "test"}],
            response_model=Ticket,
            max_retries=0,
        )

    assert exc_info.value.attempts == 1
    assert exc_info.value.response_model is Ticket


def test_complete_structured_rejects_stream() -> None:
    with pytest.raises(ValueError, match="stream"):
        complete_structured(
            messages=[{"role": "user", "content": "x"}],
            response_model=Ticket,
            stream=True,
        )


def test_complete_structured_rejects_tools_override() -> None:
    with pytest.raises(ValueError, match="tools"):
        complete_structured(
            messages=[{"role": "user", "content": "x"}],
            response_model=Ticket,
            tools=[],
        )
