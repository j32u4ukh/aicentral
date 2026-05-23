"""SEGMENT_COMPRESS：每輪回傳前先呼叫向量化 API。"""

from unittest.mock import MagicMock, patch

from aicentral import Chat, HistoryPolicy


@patch("aicentral.history.embedding", return_value=[0.5] * 4)
@patch("aicentral.chat.complete", return_value="reply")
def test_segment_compress_embeds_before_return(
    mock_complete: MagicMock,
    mock_embed: MagicMock,
) -> None:
    chat = Chat(
        max_messages=100,
        history_policy=HistoryPolicy.SEGMENT_COMPRESS,
        system="",
    )
    chat.complete("hello")

    mock_complete.assert_called_once()
    mock_embed.assert_called_once()
    assert len(chat.history._embeddings) == 2
    assert chat.history._embeddings[0] is not None
