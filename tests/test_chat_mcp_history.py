"""Chat + include_tool_messages_in_history。"""

from unittest.mock import MagicMock, patch

from aicentral import Chat


@patch("aicentral.mcp.orchestrator.invoke_resolved")
@patch("aicentral.mcp.orchestrator.resolve_fallback_chain")
@patch("aicentral.mcp.orchestrator.get_config")
def test_chat_records_mcp_trail_in_history(
    mock_get_config: MagicMock,
    mock_chain: MagicMock,
    mock_invoke: MagicMock,
) -> None:
    from aicentral.config.schema import AICentralConfig, MCPServerEntry, MCPSettings
    from aicentral.mcp.manager import MCPManager

    cfg = AICentralConfig(
        mcp_servers={
            "demo": MCPServerEntry(transport="http", url="https://example.com/mcp"),
        },
        mcp_settings=MCPSettings(tool_name_prefix=True),
    )
    mock_get_config.return_value = cfg
    mock_chain.return_value = [MagicMock(model_label="test")]

    tool_call_raw = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "demo__search",
                                "arguments": "{}",
                            },
                        }
                    ],
                }
            }
        ]
    }
    final_raw = {
        "choices": [{"message": {"role": "assistant", "content": "完成"}}],
    }
    mock_invoke.side_effect = [tool_call_raw, final_raw]

    mgr = MCPManager(cfg)
    with patch.object(
        mgr,
        "list_tools",
        return_value=[
            {"name": "demo__search", "inputSchema": {}, "mcp_server": "demo"},
        ],
    ):
        with patch.object(mgr, "call_tool", return_value="ok"):
            with patch("aicentral.mcp.orchestrator.MCPManager.from_config", return_value=mgr):
                chat = Chat.with_mcp(
                    ["demo"],
                    include_tool_messages_in_history=True,
                    system="",
                )
                assert chat.ask("查資料") == "完成"

    messages = chat.messages
    assert len(messages) == 4
    assert messages[0] == {"role": "user", "content": "查資料"}
    assert messages[1].get("tool_calls")
    assert messages[2]["role"] == "tool"
    assert messages[3] == {"role": "assistant", "content": "完成"}


@patch("aicentral.mcp.orchestrator.invoke_resolved")
@patch("aicentral.mcp.orchestrator.resolve_fallback_chain")
@patch("aicentral.mcp.orchestrator.get_config")
def test_chat_mcp_trail_second_turn_includes_prior_tools(
    mock_get_config: MagicMock,
    mock_chain: MagicMock,
    mock_invoke: MagicMock,
) -> None:
    from aicentral.config.schema import AICentralConfig, MCPServerEntry, MCPSettings
    from aicentral.mcp.manager import MCPManager

    cfg = AICentralConfig(
        mcp_servers={
            "demo": MCPServerEntry(transport="http", url="https://example.com/mcp"),
        },
        mcp_settings=MCPSettings(tool_name_prefix=True),
    )
    mock_get_config.return_value = cfg
    mock_chain.return_value = [MagicMock(model_label="test")]

    direct = {
        "choices": [{"message": {"role": "assistant", "content": "第二輪"}}],
    }
    mock_invoke.return_value = direct

    mgr = MCPManager(cfg)
    with patch.object(
        mgr,
        "list_tools",
        return_value=[
            {"name": "demo__search", "inputSchema": {}, "mcp_server": "demo"},
        ],
    ):
        with patch("aicentral.mcp.orchestrator.MCPManager.from_config", return_value=mgr):
            chat = Chat.with_mcp(
                ["demo"],
                include_tool_messages_in_history=True,
                system="",
            )
            chat.history.extend(
                [
                    {"role": "user", "content": "第一輪"},
                    {"role": "assistant", "tool_calls": [{"id": "c1"}]},
                    {"role": "tool", "tool_call_id": "c1", "content": "x"},
                    {"role": "assistant", "content": "第一輪答"},
                ]
            )
            chat.ask("第二輪")

    sent = mock_invoke.call_args[0][1]
    assert sent[0]["content"] == "第一輪"
    assert sent[1].get("tool_calls")
    assert sent[-1]["content"] == "第二輪"


@patch("aicentral.chat.complete", return_value="only-final")
def test_chat_without_trail_flag_keeps_pair_history(mock_complete: MagicMock) -> None:
    chat = Chat.with_mcp(["demo"], include_tool_messages_in_history=False, system="")
    chat.ask("hi")
    assert chat.messages == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "only-final"},
    ]
    assert "return_message_trail" not in mock_complete.call_args.kwargs
