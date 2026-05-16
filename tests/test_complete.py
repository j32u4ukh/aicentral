from unittest.mock import MagicMock, patch

import httpx
import pytest

from aicentral import complete
from aicentral.exceptions import ProviderError
from aicentral.providers.openai_compat import chat_completions


def test_chat_completions_returns_content() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "你好！"}}],
    }

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_response

    with patch("aicentral.providers.openai_compat.httpx.Client", return_value=mock_client):
        text = chat_completions(
            messages=[{"role": "user", "content": "hi"}],
            model="llama3.2",
            base_url="http://localhost:11434/v1",
        )

    assert text == "你好！"
    mock_client.post.assert_called_once()
    call_kwargs = mock_client.post.call_args
    assert call_kwargs[0][0] == "http://localhost:11434/v1/chat/completions"
    assert call_kwargs[1]["json"]["model"] == "llama3.2"


def test_chat_completions_http_error() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.text = "model not found"
    mock_response.reason_phrase = "Not Found"

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_response

    with patch("aicentral.providers.openai_compat.httpx.Client", return_value=mock_client):
        with pytest.raises(ProviderError) as exc_info:
            chat_completions(
                messages=[{"role": "user", "content": "hi"}],
                model="missing",
                base_url="http://localhost:11434/v1",
            )

    assert exc_info.value.status_code == 404


def test_chat_completions_connection_error() -> None:
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.side_effect = httpx.ConnectError("connection refused")

    with patch("aicentral.providers.openai_compat.httpx.Client", return_value=mock_client):
        with pytest.raises(ProviderError, match="無法連線"):
            chat_completions(
                messages=[{"role": "user", "content": "hi"}],
                model="llama3.2",
                base_url="http://localhost:11434/v1",
            )


@patch("aicentral.client.chat_completions", return_value="from client")
def test_complete_delegates_to_provider(mock_chat: MagicMock) -> None:
    result = complete([{"role": "user", "content": "test"}], model="llama3.2")
    assert result == "from client"
    mock_chat.assert_called_once()
    assert mock_chat.call_args.kwargs["model"] == "llama3.2"
