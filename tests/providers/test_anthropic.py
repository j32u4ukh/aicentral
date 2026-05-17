from unittest.mock import MagicMock, patch

import pytest

from aicentral.core.errors import ProviderError
from aicentral.providers.anthropic import chat_completions, chat_completions_raw


def test_chat_completions_anthropic() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "content": [{"type": "text", "text": "你好"}],
    }

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_response

    with patch("aicentral.providers.anthropic.httpx.Client", return_value=mock_client):
        text = chat_completions(
            messages=[{"role": "user", "content": "hi"}],
            model="claude-sonnet-4-20250514",
            api_key="sk-ant",
        )

    assert text == "你好"
    call = mock_client.post.call_args
    assert call[0][0].endswith("/v1/messages")
    assert call[1]["headers"]["x-api-key"] == "sk-ant"


def test_chat_completions_raw_openai_shape() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "content": [{"type": "text", "text": "ok"}],
    }

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_response

    with patch("aicentral.providers.anthropic.httpx.Client", return_value=mock_client):
        data = chat_completions_raw(
            messages=[{"role": "user", "content": "hi"}],
            model="claude-sonnet-4-20250514",
            api_key="sk-ant",
        )

    assert data["choices"][0]["message"]["content"] == "ok"


def test_chat_completions_missing_key() -> None:
    with pytest.raises(ProviderError, match="api_key"):
        chat_completions(
            messages=[{"role": "user", "content": "hi"}],
            model="claude",
            api_key=None,
        )
