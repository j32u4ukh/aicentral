from unittest.mock import MagicMock, patch

from pydantic import BaseModel

from aicentral import Chat


class Ticket(BaseModel):
    title: str
    priority: int


@patch("aicentral.chat.complete_structured")
def test_chat_complete_structured_stateful(mock_cs: MagicMock) -> None:
    mock_cs.return_value = Ticket(title="t", priority=1)
    chat = Chat(system="")
    result = chat.complete_structured("建立工單", response_model=Ticket)

    assert result.title == "t"
    assert len(chat.messages) == 2
    assert chat.messages[1]["role"] == "assistant"
    assert '"title"' in chat.messages[1]["content"]
