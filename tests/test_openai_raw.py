from unittest.mock import MagicMock, patch

from aicentral.providers.openai import chat_completions_raw


def test_chat_completions_raw_returns_dict() -> None:
    payload = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "ticket",
                                "arguments": "{}",
                            }
                        }
                    ],
                }
            }
        ]
    }
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = payload

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_response

    with patch("aicentral.providers.openai.httpx.Client", return_value=mock_client):
        data = chat_completions_raw(
            messages=[{"role": "user", "content": "hi"}],
            model="gemma4:e2b",
            tools=[{"type": "function", "function": {"name": "ticket"}}],
        )

    assert data == payload
    assert "tools" in mock_client.post.call_args.kwargs["json"]
