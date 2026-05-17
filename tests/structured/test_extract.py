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
