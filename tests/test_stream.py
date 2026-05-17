from unittest.mock import MagicMock, patch

import pytest

from aicentral import Chat, complete
from aicentral.exceptions import ProviderError
from aicentral.providers.openai import chat_completions_stream
from aicentral.providers.streaming import extract_delta_content, parse_sse_data_line


def test_parse_sse_data_line() -> None:
    assert parse_sse_data_line('data: {"choices":[]}') == {"choices": []}
    assert parse_sse_data_line("data: [DONE]") is None
    assert parse_sse_data_line("") is None


def test_extract_delta_content() -> None:
    chunk = {"choices": [{"delta": {"content": "你好"}}]}
    assert extract_delta_content(chunk) == "你好"
    assert extract_delta_content({"choices": [{"delta": {}}]}) is None


def test_chat_completions_stream_yields_deltas() -> None:
    sse_lines = [
        'data: {"choices":[{"delta":{"content":"你"}}]}',
        'data: {"choices":[{"delta":{"content":"好"}}]}',
        "data: [DONE]",
    ]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.iter_lines.return_value = iter(sse_lines)
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.stream.return_value = mock_response

    with patch("aicentral.providers.openai.httpx.Client", return_value=mock_client):
        deltas = list(
            chat_completions_stream(
                messages=[{"role": "user", "content": "hi"}],
                model="gemma4:e2b",
                base_url="http://localhost:11434/v1",
            )
        )

    assert deltas == ["你", "好"]
    payload = mock_client.stream.call_args.kwargs["json"]
    assert payload["stream"] is True


@patch("aicentral.providers.openai.chat_completions_stream")
def test_complete_stream_delegates(mock_stream: MagicMock) -> None:
    mock_stream.return_value = iter(["a", "b"])
    result = complete([{"role": "user", "content": "hi"}], stream=True)
    assert list(result) == ["a", "b"]
    mock_stream.assert_called_once()


@patch("aicentral.chat.complete")
def test_chat_stateful_stream_records_full_history(mock_complete: MagicMock) -> None:
    mock_complete.return_value = iter(["台", "北"])

    chat = Chat(system="")
    deltas = list(chat.complete("首都？", stream=True))

    assert deltas == ["台", "北"]
    assert len(chat.messages) == 2
    assert chat.messages[1] == {"role": "assistant", "content": "台北"}


@patch("aicentral.chat.complete")
def test_chat_stateful_stream_no_history_on_mid_failure(mock_complete: MagicMock) -> None:
    def _broken() -> MagicMock:
        yield "x"
        raise ProviderError("斷線")

    mock_complete.return_value = _broken()

    chat = Chat(system="")
    stream = chat.complete("hi", stream=True)
    with pytest.raises(ProviderError):
        list(stream)
    assert chat.messages == []


@patch("aicentral.chat.complete")
def test_chat_stateless_stream_no_history(mock_complete: MagicMock) -> None:
    from aicentral import ChatMode

    mock_complete.return_value = iter(["ok"])
    chat = Chat(mode=ChatMode.STATELESS, system="")
    list(chat.complete("q", stream=True))
    assert chat.messages == []
