from unittest.mock import MagicMock, patch

import pytest

from aicentral import Chat, HistoryPolicy
from aicentral.exceptions import HistoryOverflowError


@patch("aicentral.chat.complete", return_value="r")
def test_manual_raises_on_overflow(mock_complete: MagicMock) -> None:
    chat = Chat(max_messages=4, history_policy=HistoryPolicy.MANUAL, system="")
    chat.complete("a")
    chat.complete("b")

    with pytest.raises(HistoryOverflowError):
        chat.complete("c")


@patch("aicentral.chat.complete", return_value="r")
def test_delete_removes_indices(mock_complete: MagicMock) -> None:
    chat = Chat(max_messages=100, history_policy=HistoryPolicy.MANUAL, system="")
    chat.complete("a")
    chat.complete("b")
    chat.delete([0, 1])
    assert len(chat.messages) == 2


@patch("aicentral.chat.complete", return_value="r")
def test_trim_keep_last(mock_complete: MagicMock) -> None:
    chat = Chat(max_messages=100, history_policy=HistoryPolicy.MANUAL, system="")
    for label in ("a", "b", "c"):
        chat.complete(label)
    chat.trim(keep_last=2)
    assert len(chat.messages) == 2
    assert chat.messages[0]["content"] == "c"


@patch("aicentral.history.embedding", side_effect=RuntimeError("mock: skip vector"))
@patch("aicentral.history.complete", return_value="summary")
@patch("aicentral.chat.complete")
def test_segment_compress(
    mock_chat_complete: MagicMock,
    _mock_hist_complete: MagicMock,
    _mock_embed: MagicMock,
) -> None:
    mock_chat_complete.side_effect = ["a1", "a2", "a3"]

    chat = Chat(
        max_messages=4,
        history_policy=HistoryPolicy.SEGMENT_COMPRESS,
        system="",
    )
    chat.complete("m1")
    chat.complete("m2")
    chat.complete("m3")

    assert any("[摘要]" in m.get("content", "") for m in chat.messages)
    assert chat._turn_count() <= 4
