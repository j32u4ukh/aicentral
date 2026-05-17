from unittest.mock import AsyncMock, patch

import pytest

from aicentral.config.schema import AICentralConfig, MCPServerEntry, MCPSettings
from aicentral.mcp.manager import MCPManager


def _cfg() -> AICentralConfig:
    return AICentralConfig(
        mcp_servers={
            "demo": MCPServerEntry(
                transport="http",
                url="https://example.com/mcp",
            ),
        },
        mcp_settings=MCPSettings(tool_name_prefix=True),
    )


@patch("aicentral.mcp.manager.alist_tools", new_callable=AsyncMock)
def test_list_tools_prefixed(mock_list: AsyncMock) -> None:
    mock_list.return_value = [{"name": "search", "description": "d", "inputSchema": {}}]
    mgr = MCPManager(_cfg())
    tools = mgr.list_tools("demo")
    assert tools[0]["name"] == "demo__search"
    assert tools[0]["mcp_server"] == "demo"


def test_unknown_server() -> None:
    mgr = MCPManager(_cfg())
    with pytest.raises(Exception, match="未知 MCP server"):
        mgr.list_tools("missing")


def test_parse_server_url() -> None:
    assert MCPManager.parse_server_url("aicentral/mcp/demo") == "demo"
    assert MCPManager.parse_server_url("https://other") is None
