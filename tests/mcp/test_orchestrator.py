import json
from unittest.mock import MagicMock, patch

import pytest

from aicentral.config.schema import AICentralConfig, MCPServerEntry, MCPSettings
from aicentral.mcp.manager import MCPError, MCPManager
from aicentral.mcp.orchestrator import (
    extract_tool_calls,
    mcp_tool_to_openai,
    merge_openai_tools,
    resolve_mcp_server_names,
    run_tool_calls,
    serialize_tool_result,
)


def _mgr() -> MCPManager:
    return MCPManager(
        AICentralConfig(
            mcp_servers={
                "demo": MCPServerEntry(
                    transport="http",
                    url="https://example.com/mcp",
                ),
            },
            mcp_settings=MCPSettings(tool_name_prefix=True),
        )
    )


def test_mcp_tool_to_openai() -> None:
    tool = mcp_tool_to_openai(
        {
            "name": "demo__search",
            "description": "搜尋",
            "inputSchema": {
                "type": "object",
                "properties": {"q": {"type": "string"}},
            },
        }
    )
    assert tool["type"] == "function"
    assert tool["function"]["name"] == "demo__search"
    assert tool["function"]["description"] == "搜尋"


def test_merge_openai_tools_mcp_overrides_user() -> None:
    user = [{"type": "function", "function": {"name": "x", "parameters": {}}}]
    mcp = [{"type": "function", "function": {"name": "x", "parameters": {"type": "object"}}}]
    merged = merge_openai_tools(mcp, user)
    assert len(merged) == 1
    assert merged[0]["function"]["parameters"]["type"] == "object"


def test_resolve_mcp_server_names_all() -> None:
    names = resolve_mcp_server_names("all", _mgr())
    assert names == ["demo"]


def test_resolve_unknown_server() -> None:
    with pytest.raises(MCPError, match="未知"):
        resolve_mcp_server_names(["missing"], _mgr())


def test_run_tool_calls() -> None:
    mgr = MagicMock()
    mgr.call_tool.return_value = {"ok": True}
    name_to_server = {"demo__search": "demo"}
    tool_calls = [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "demo__search", "arguments": '{"q": "hi"}'},
        }
    ]
    msgs = run_tool_calls(tool_calls, mgr=mgr, name_to_server=name_to_server)
    assert len(msgs) == 1
    assert msgs[0]["role"] == "tool"
    assert msgs[0]["tool_call_id"] == "call_1"
    mgr.call_tool.assert_called_once_with("demo", "demo__search", {"q": "hi"})


def test_extract_tool_calls_empty() -> None:
    assert extract_tool_calls({"role": "assistant", "content": "hi"}) == []


def test_serialize_tool_result() -> None:
    assert serialize_tool_result({"a": 1}) == '{"a": 1}'
