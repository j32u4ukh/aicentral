"""Chat + MCP 簡化 API。"""

from unittest.mock import MagicMock, patch

from aicentral import Chat, complete


@patch("aicentral.core.client.complete_with_mcp_loop", return_value="mcp-reply")
def test_complete_accepts_question_string(mock_loop: MagicMock) -> None:
    reply = complete("什麼是 MCP？", mcp_servers=["demo"])
    assert reply == "mcp-reply"
    messages = mock_loop.call_args[0][0]
    assert messages[-1] == {"role": "user", "content": "什麼是 MCP？"}


@patch("aicentral.chat.complete", return_value="chat-mcp-reply")
def test_chat_with_mcp_ask(mock_complete: MagicMock) -> None:
    chat = Chat.with_mcp(["deepwiki"], model="local")
    assert chat.ask("查 README") == "chat-mcp-reply"
    mock_complete.assert_called_once()
    kw = mock_complete.call_args.kwargs
    assert kw["mcp_servers"] == ["deepwiki"]
    assert kw["messages"][-1] == {"role": "user", "content": "查 README"}


@patch("aicentral.mcp.orchestrator.complete_with_mcp_loop", return_value="ok")
def test_ask_mcp(mock_loop: MagicMock) -> None:
    from aicentral import ask_mcp

    assert ask_mcp("hi", mcp_servers=["demo"]) == "ok"
    assert mock_loop.call_args[0][0] == [{"role": "user", "content": "hi"}]
