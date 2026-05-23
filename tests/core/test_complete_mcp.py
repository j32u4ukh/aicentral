from unittest.mock import MagicMock, patch

import pytest

from aicentral import complete
from aicentral.config.schema import AICentralConfig, MCPServerEntry, MCPSettings
from aicentral.core.errors import ProviderError
from aicentral.mcp.manager import MCPError, MCPManager


def _cfg() -> AICentralConfig:
    return AICentralConfig(
        mcp_servers={
            "demo": MCPServerEntry(transport="http", url="https://example.com/mcp"),
        },
        mcp_settings=MCPSettings(tool_name_prefix=True),
    )


@patch("aicentral.mcp.orchestrator.invoke_resolved")
@patch("aicentral.mcp.orchestrator.resolve_fallback_chain")
@patch("aicentral.mcp.orchestrator.get_config")
def test_complete_mcp_one_round(
    mock_get_config: MagicMock,
    mock_chain: MagicMock,
    mock_invoke: MagicMock,
) -> None:
    mock_get_config.return_value = _cfg()
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
                                "arguments": '{"q": "x"}',
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

    mgr = MCPManager(_cfg())

    with patch.object(
        mgr,
        "list_tools",
        return_value=[
            {
                "name": "demo__search",
                "description": "d",
                "inputSchema": {},
                "mcp_server": "demo",
            }
        ],
    ):
        mock_call_tool = MagicMock(return_value="result")
        with patch.object(mgr, "call_tool", mock_call_tool):
            with patch(
                "aicentral.mcp.orchestrator.MCPManager.from_config",
                return_value=mgr,
            ):
                reply = complete(
                    [{"role": "user", "content": "查資料"}],
                    mcp_servers=["demo"],
                    max_tool_rounds=5,
                )

    assert reply == "完成"
    assert mock_invoke.call_count == 2
    mock_call_tool.assert_called_once()


@patch("aicentral.mcp.orchestrator.invoke_resolved")
@patch("aicentral.mcp.orchestrator.resolve_fallback_chain")
@patch("aicentral.mcp.orchestrator.get_config")
def test_complete_mcp_return_message_trail(
    mock_get_config: MagicMock,
    mock_chain: MagicMock,
    mock_invoke: MagicMock,
) -> None:
    mock_get_config.return_value = _cfg()
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
                                "arguments": '{"q": "x"}',
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

    mgr = MCPManager(_cfg())
    with patch.object(
        mgr,
        "list_tools",
        return_value=[
            {
                "name": "demo__search",
                "description": "d",
                "inputSchema": {},
                "mcp_server": "demo",
            }
        ],
    ):
        with patch.object(mgr, "call_tool", return_value="tool-result"):
            with patch(
                "aicentral.mcp.orchestrator.MCPManager.from_config",
                return_value=mgr,
            ):
                result = complete(
                    [{"role": "user", "content": "查資料"}],
                    mcp_servers=["demo"],
                    return_message_trail=True,
                )

    assert isinstance(result, tuple)
    reply, trail = result
    assert reply == "完成"
    assert len(trail) == 3
    assert trail[0].get("tool_calls")
    assert trail[1]["role"] == "tool"
    assert trail[1]["tool_call_id"] == "call_1"
    assert trail[2]["role"] == "assistant"
    assert trail[2]["content"] == "完成"


@patch("aicentral.mcp.orchestrator.invoke_resolved")
@patch("aicentral.mcp.orchestrator.resolve_fallback_chain")
@patch("aicentral.mcp.orchestrator.get_config")
def test_complete_mcp_error_no_provider_fallback(
    mock_get_config: MagicMock,
    mock_chain: MagicMock,
    mock_invoke: MagicMock,
) -> None:
    mock_get_config.return_value = _cfg()
    mock_chain.return_value = [MagicMock(model_label="a"), MagicMock(model_label="b")]
    mock_invoke.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "c1",
                            "function": {"name": "demo__search", "arguments": "{}"},
                        }
                    ],
                }
            }
        ]
    }

    mgr = MCPManager(_cfg())
    with patch.object(
        mgr,
        "list_tools",
        return_value=[
            {"name": "demo__search", "inputSchema": {}, "mcp_server": "demo"},
        ],
    ):
        with patch.object(mgr, "call_tool", side_effect=MCPError("tool fail")):
            with patch("aicentral.mcp.orchestrator.MCPManager.from_config", return_value=mgr):
                with pytest.raises(MCPError, match="tool fail"):
                    complete(
                        [{"role": "user", "content": "x"}],
                        mcp_servers=["demo"],
                    )
    assert mock_invoke.call_count == 1


def test_complete_mcp_rejects_stream() -> None:
    with pytest.raises(ValueError, match="stream"):
        complete(
            [{"role": "user", "content": "x"}],
            mcp_servers=["demo"],
            stream=True,
        )


def test_complete_without_mcp_unchanged() -> None:
    with patch("aicentral.core.client.complete_with_fallback", return_value="ok") as mock_cf:
        assert complete([{"role": "user", "content": "hi"}]) == "ok"
        mock_cf.assert_called_once()
