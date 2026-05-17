from aicentral.structured.retry import append_retry_hint


def test_append_retry_hint_adds_user_message() -> None:
    messages = [{"role": "user", "content": "hello"}]
    updated = append_retry_hint(messages, "priority: out of range")
    assert len(updated) == 2
    assert updated[-1]["role"] == "user"
    assert "priority" in updated[-1]["content"]
    assert "function" in updated[-1]["content"]
