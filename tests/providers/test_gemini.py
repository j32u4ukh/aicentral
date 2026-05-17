from unittest.mock import MagicMock, patch

from aicentral.providers.gemini import chat_completions, chat_completions_raw


def test_chat_completions_gemini() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": "回覆"}]}}],
    }

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_response

    with patch("aicentral.providers.gemini.httpx.Client", return_value=mock_client):
        text = chat_completions(
            messages=[{"role": "user", "content": "hi"}],
            model="gemini-2.0-flash",
            api_key="gem-key",
        )

    assert text == "回覆"
    call = mock_client.post.call_args
    assert "generateContent" in call[0][0]
    assert call[1]["params"]["key"] == "gem-key"


def test_chat_completions_raw_openai_shape() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": "json"}]}}],
    }

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_response

    with patch("aicentral.providers.gemini.httpx.Client", return_value=mock_client):
        data = chat_completions_raw(
            messages=[{"role": "user", "content": "hi"}],
            model="gemini-2.0-flash",
            api_key="gem-key",
        )

    assert data["choices"][0]["message"]["content"] == "json"
