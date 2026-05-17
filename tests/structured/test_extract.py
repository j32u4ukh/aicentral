from aicentral.structured.extract import from_chat_completion


def test_extract_tool_calls_arguments() -> None:
    data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "ticket",
                                "arguments": '{"title": "down", "priority": 3}',
                            }
                        }
                    ],
                }
            }
        ]
    }
    assert from_chat_completion(data) == {"title": "down", "priority": 3}


def test_extract_invalid_json_returns_none() -> None:
    data = {
        "choices": [
            {
                "message": {
                    "tool_calls": [{"function": {"arguments": "not-json"}}],
                }
            }
        ]
    }
    assert from_chat_completion(data) is None


def test_extract_missing_tool_calls_returns_none() -> None:
    data = {"choices": [{"message": {"role": "assistant", "content": "hello"}}]}
    assert from_chat_completion(data) is None


def test_extract_json_mode_from_content() -> None:
    data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": '{"title": "ok", "priority": 2}',
                }
            }
        ]
    }
    assert from_chat_completion(data, mode="json") == {"title": "ok", "priority": 2}


def test_extract_json_mode_strips_markdown_fence() -> None:
    data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": '```json\n{"title": "x", "priority": 1}\n```',
                }
            }
        ]
    }
    assert from_chat_completion(data, mode="json") == {"title": "x", "priority": 1}
