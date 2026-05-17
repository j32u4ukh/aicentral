from unittest.mock import MagicMock, patch

import pytest

from aicentral import Chat, ChatMode, HistoryPolicy
from aicentral.exceptions import ProviderError


@patch("aicentral.chat.complete", return_value="reply-1")
def test_stateful_accumulates_history(mock_complete: MagicMock) -> None:
    chat = Chat(system="")
    assert chat.complete("hello") == "reply-1"
    assert chat.complete("again") == "reply-1"

    assert len(chat.messages) == 4
    assert chat.messages[0] == {"role": "user", "content": "hello"}
    assert chat.messages[1] == {"role": "assistant", "content": "reply-1"}

    second_call_messages = mock_complete.call_args_list[1].kwargs["messages"]
    assert len(second_call_messages) == 3
    assert second_call_messages[-1] == {"role": "user", "content": "again"}


@patch("aicentral.chat.complete", return_value="only")
def test_stateless_does_not_accumulate(mock_complete: MagicMock) -> None:
    chat = Chat(mode=ChatMode.STATELESS, system="")
    chat.complete("first")
    chat.complete("second")

    assert chat.messages == []
    for call in mock_complete.call_args_list:
        msgs = call.kwargs["messages"]
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"


@patch("aicentral.chat.complete", return_value="ok")
def test_stateless_with_context(mock_complete: MagicMock) -> None:
    chat = Chat(mode=ChatMode.STATELESS, system="")
    context = [
        {"role": "user", "content": "prior"},
        {"role": "assistant", "content": "prior-reply"},
    ]
    chat.complete("summarize", context=context)

    msgs = mock_complete.call_args.kwargs["messages"]
    assert len(msgs) == 3
    assert msgs[-1]["content"] == "summarize"


@patch("aicentral.chat.complete", return_value="ok")
def test_stateful_rollback_on_provider_error(mock_complete: MagicMock) -> None:
    mock_complete.side_effect = [ProviderError("fail"), "ok"]
    chat = Chat(system="")

    with pytest.raises(ProviderError):
        chat.complete("bad")

    assert chat.messages == []
    chat.complete("good")
    assert len(chat.messages) == 2


@patch("aicentral.chat.complete", return_value="r")
def test_drop_oldest_pair_trims(mock_complete: MagicMock) -> None:
    chat = Chat(max_messages=4, history_policy=HistoryPolicy.DROP_OLDEST_PAIR, system="")

    for index in range(3):
        chat.complete(f"u{index}")

    assert chat._turn_count() == 4
    assert chat.messages[0]["content"] == "u1"


@patch("aicentral.chat.complete", return_value="r")
def test_drop_oldest_trims_one(mock_complete: MagicMock) -> None:
    chat = Chat(
        max_messages=2,
        history_policy=HistoryPolicy.DROP_OLDEST,
        system="",
    )
    chat.complete("a")
    chat.complete("b")

    assert len(chat.messages) == 2
    assert chat.messages[0]["content"] == "b"


@patch("aicentral.chat.complete")
def test_classmethod_constructors(mock_complete: MagicMock) -> None:
    mock_complete.return_value = "x"
    s = Chat.stateful(system="")
    n = Chat.stateless(system="")
    assert s.mode == ChatMode.STATEFUL
    assert n.mode == ChatMode.STATELESS
