from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel, Field

from aicentral import complete_structured
from aicentral.core.errors import StructuredValidationError


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


@patch("aicentral.core.client.invoke_resolved")
def test_complete_structured_success(mock_invoke: MagicMock) -> None:
    mock_invoke.return_value = _raw_with_args('{"title": "伺服器當機", "priority": 4}')

    ticket = complete_structured(
        messages=[{"role": "user", "content": "很急"}],
        response_model=Ticket,
        model="ollama/gemma4:e2b",
    )

    assert isinstance(ticket, Ticket)
    assert ticket.title == "伺服器當機"
    assert mock_invoke.call_count == 1


@patch("aicentral.core.client.invoke_resolved")
def test_complete_structured_single_call_on_validation_error(mock_invoke: MagicMock) -> None:
    mock_invoke.return_value = _raw_with_args('{"title": "x", "priority": 99}')

    with pytest.raises(StructuredValidationError) as exc_info:
        complete_structured(
            messages=[{"role": "user", "content": "test"}],
            response_model=Ticket,
        )

    assert exc_info.value.failure_kind.value == "validation"
    assert mock_invoke.call_count == 1


def test_complete_structured_rejects_max_retries_kwarg() -> None:
    with pytest.raises(ValueError, match="max_retries"):
        complete_structured(
            messages=[{"role": "user", "content": "x"}],
            response_model=Ticket,
            max_retries=1,
        )


def test_complete_structured_rejects_stream() -> None:
    with pytest.raises(ValueError, match="stream"):
        complete_structured(
            messages=[{"role": "user", "content": "x"}],
            response_model=Ticket,
            stream=True,
        )


@patch("aicentral.core.client.invoke_resolved")
def test_complete_structured_json_mode(mock_invoke: MagicMock) -> None:
    mock_invoke.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": '{"title": "json-path", "priority": 3}',
                }
            }
        ]
    }

    ticket = complete_structured(
        messages=[{"role": "user", "content": "test"}],
        response_model=Ticket,
        mode="json",
    )
    assert ticket.title == "json-path"
    call_kwargs = mock_invoke.call_args.kwargs
    assert "tools" not in call_kwargs
