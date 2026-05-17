from unittest.mock import MagicMock, patch

from aicentral import Chat, ChatMode


@patch("aicentral.chat.complete", return_value="ok")
def test_set_mode_to_stateless_clears_history(mock_complete: MagicMock) -> None:
    chat = Chat(system="")
    chat.complete("remember")
    assert len(chat.messages) == 2

    chat.set_mode(ChatMode.STATELESS)
    assert chat.mode == ChatMode.STATELESS
    assert chat.messages == []

    chat.complete("forget?")
    msgs = mock_complete.call_args.kwargs["messages"]
    assert len(msgs) == 1


@patch("aicentral.chat.complete", return_value="ok")
def test_set_mode_keep_history(mock_complete: MagicMock) -> None:
    chat = Chat(system="")
    chat.complete("stored")
    chat.set_mode(ChatMode.STATELESS, clear_on_stateless=False)
    assert chat.messages == []
    assert len(chat._history) == 2
    chat.set_mode(ChatMode.STATEFUL)
    assert len(chat.messages) == 2


@patch("aicentral.chat.complete", return_value="ok")
def test_clear(mock_complete: MagicMock) -> None:
    chat = Chat(system="")
    chat.complete("hi")
    chat.clear()
    assert chat.messages == []
