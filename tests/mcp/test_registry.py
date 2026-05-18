from unittest.mock import AsyncMock, patch

import pytest

from aicentral.config.schema import AICentralConfig, MCPServerEntry, MCPSettings
from aicentral.mcp import (
    MCPManager,
    clear_mcp_registry,
    register_mcp_server,
    register_mcp_servers,
    registered_mcp_servers,
    unregister_mcp_server,
)


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    clear_mcp_registry()
    yield
    clear_mcp_registry()


def test_register_mcp_server_with_kwargs() -> None:
    register_mcp_server("runtime", transport="http", url="https://runtime.example/mcp")
    assert "runtime" in registered_mcp_servers()


def test_register_mcp_servers_batch() -> None:
    register_mcp_servers(
        {
            "a": {"transport": "http", "url": "https://a.example/mcp"},
            "b": MCPServerEntry(transport="http", url="https://b.example/mcp"),
        }
    )
    assert set(registered_mcp_servers()) == {"a", "b"}


def test_register_rejects_entry_and_kwargs() -> None:
    with pytest.raises(ValueError, match="entry"):
        register_mcp_server(
            "x",
            MCPServerEntry(transport="http", url="https://x.example/mcp"),
            transport="http",
        )


@patch("aicentral.mcp.manager.alist_tools", new_callable=AsyncMock)
def test_manager_merges_yaml_and_registry(mock_list: AsyncMock) -> None:
    mock_list.return_value = [{"name": "t", "description": "d", "inputSchema": {}}]
    cfg = AICentralConfig(
        mcp_servers={
            "yaml_srv": MCPServerEntry(transport="http", url="https://yaml.example/mcp"),
        },
        mcp_settings=MCPSettings(tool_name_prefix=False),
    )
    register_mcp_server("reg_srv", transport="http", url="https://reg.example/mcp")
    mgr = MCPManager(cfg)
    yaml_tools = mgr.list_tools("yaml_srv")
    reg_tools = mgr.list_tools("reg_srv")
    assert yaml_tools[0]["name"] == "t"
    assert reg_tools[0]["name"] == "t"
    assert mock_list.call_count == 2


@patch("aicentral.mcp.manager.alist_tools", new_callable=AsyncMock)
def test_registry_overrides_yaml_same_name(mock_list: AsyncMock) -> None:
    mock_list.return_value = [{"name": "t", "description": "", "inputSchema": {}}]
    cfg = AICentralConfig(
        mcp_servers={
            "demo": MCPServerEntry(transport="http", url="https://yaml.example/mcp"),
        },
    )
    register_mcp_server("demo", transport="http", url="https://override.example/mcp")
    mgr = MCPManager(cfg)
    mgr.list_tools("demo")
    assert mock_list.call_args[0][0].url == "https://override.example/mcp"


@patch("aicentral.mcp.manager.alist_tools", new_callable=AsyncMock)
def test_from_config_includes_registry(mock_list: AsyncMock) -> None:
    mock_list.return_value = [{"name": "t", "description": "", "inputSchema": {}}]
    register_mcp_server("only_reg", transport="http", url="https://only.example/mcp")
    mgr = MCPManager(AICentralConfig())
    mgr.list_tools("only_reg")
    mock_list.assert_called_once()


def test_unregister_mcp_server() -> None:
    register_mcp_server("tmp", transport="http", url="https://tmp.example/mcp")
    unregister_mcp_server("tmp")
    assert registered_mcp_servers() == {}
