from unittest.mock import MagicMock, patch

from aicentral.providers.gemini import (
    build_generate_content_url,
    chat_completions,
    chat_completions_raw,
)


def test_build_generate_content_url() -> None:
    url = build_generate_content_url("gemini-3.5-flash")
    assert (
        url
        == "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent"
    )
    url_pro = build_generate_content_url(
        "gemini-3.1-pro",
        base_url="https://generativelanguage.googleapis.com/v1beta/",
    )
    assert url_pro.endswith("/models/gemini-3.1-pro:generateContent")


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
    assert call[0][0] == (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.0-flash:generateContent"
    )
    assert call[1]["headers"]["X-Goog-Api-Key"] == "gem-key"
    assert "params" not in call[1] or call[1].get("params") in (None, {})


def test_chat_completions_429_sets_retry_after() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.text = '{"error":{"code":429}}'
    mock_response.reason_phrase = "Too Many Requests"
    mock_response.headers = {"retry-after": "5"}

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_response

    with patch("aicentral.providers.gemini.httpx.Client", return_value=mock_client):
        from aicentral.core.errors import ProviderError

        try:
            chat_completions(
                messages=[{"role": "user", "content": "hi"}],
                model="gemini-2.0-flash",
                api_key="gem-key",
            )
        except ProviderError as exc:
            assert exc.status_code == 429
            assert exc.failure_kind == "rate_limit"
            assert exc.retry_after_seconds == 5.0
        else:
            raise AssertionError("expected ProviderError")


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
