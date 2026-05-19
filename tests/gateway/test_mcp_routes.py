"""Gateway MCP HTTP 路由（v0.6.1）。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from aicentral.config.loader import load_config
from aicentral.gateway.app import create_app
from aicentral.mcp.registry import clear_mcp_registry, registered_mcp_servers


@pytest.fixture
def gateway_mcp_client(tmp_path: Path) -> TestClient:
    secret = tmp_path / "secret.yaml"
    secret.write_text("ollama:\n  model: x\n", encoding="utf-8")
    main = tmp_path / "aicentral.yaml"
    main.write_text(
        yaml.dump(
            {
                "gateway": {
                    "enabled": True,
                    "bind_host": "127.0.0.1",
                    "optional_token": None,
                    "reject_non_local_client": False,
                },
                "mcp_servers": {
                    "deepwiki": {
                        "transport": "http",
                        "url": "https://mcp.example.com/mcp",
                        "auth_type": "none",
                        "auth_value": "secret-from-yaml",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    load_config(path=main, secrets_path=secret, reload=True)
    clear_mcp_registry()
    client = TestClient(create_app())
    yield client
    clear_mcp_registry()


def test_list_servers_yaml_and_masks_secret(gateway_mcp_client: TestClient) -> None:
    r = gateway_mcp_client.get("/v1/mcp/servers")
    assert r.status_code == 200
    servers = r.json()["servers"]
    assert len(servers) == 1
    dw = servers[0]
    assert dw["name"] == "deepwiki"
    assert dw["source"] == "yaml"
    assert "auth_value" not in dw


def test_post_register_runtime(gateway_mcp_client: TestClient) -> None:
    r = gateway_mcp_client.post(
        "/v1/mcp/servers",
        json={
            "name": "fetch",
            "transport": "stdio",
            "command": "uvx",
            "args": ["mcp-server-fetch"],
        },
    )
    assert r.status_code == 201
    assert "fetch" in registered_mcp_servers()


def test_post_register_batch(gateway_mcp_client: TestClient) -> None:
    r = gateway_mcp_client.post(
        "/v1/mcp/servers",
        json={
            "servers": {
                "a": {"transport": "http", "url": "http://a/mcp", "auth_type": "none"},
            }
        },
    )
    assert r.status_code == 201
    assert "a" in registered_mcp_servers()


def test_get_server_not_found(gateway_mcp_client: TestClient) -> None:
    r = gateway_mcp_client.get("/v1/mcp/servers/missing")
    assert r.status_code == 404


def test_delete_yaml_only_returns_404(gateway_mcp_client: TestClient) -> None:
    r = gateway_mcp_client.delete("/v1/mcp/servers/deepwiki")
    assert r.status_code == 404


def test_delete_runtime_server(gateway_mcp_client: TestClient) -> None:
    gateway_mcp_client.post(
        "/v1/mcp/servers",
        json={
            "name": "runtime_only",
            "transport": "http",
            "url": "http://x/mcp",
            "auth_type": "none",
        },
    )
    r = gateway_mcp_client.delete("/v1/mcp/servers/runtime_only")
    assert r.status_code == 204
    assert "runtime_only" not in registered_mcp_servers()


@patch("aicentral.mcp.manager.MCPManager.list_tools", return_value=[{"name": "t1"}])
def test_list_tools(mock_list: MagicMock, gateway_mcp_client: TestClient) -> None:
    r = gateway_mcp_client.get("/v1/mcp/deepwiki/tools")
    assert r.status_code == 200
    assert r.json()["tools"][0]["name"] == "t1"
    mock_list.assert_called_once_with("deepwiki")


@patch("aicentral.mcp.manager.MCPManager.call_tool", return_value="ok")
def test_call_tool(mock_call: MagicMock, gateway_mcp_client: TestClient) -> None:
    r = gateway_mcp_client.post(
        "/v1/mcp/deepwiki/tools/deepwiki__search",
        json={"arguments": {"query": "MCP"}},
    )
    assert r.status_code == 200
    assert r.json()["result"] == "ok"
    mock_call.assert_called_once_with("deepwiki", "deepwiki__search", {"query": "MCP"})


@patch("aicentral.gateway.routes.mcp.mcp_dependency_installed", return_value=False)
def test_mcp_routes_503_without_mcp_package(
    _mock_mcp: MagicMock, gateway_mcp_client: TestClient
) -> None:
    r = gateway_mcp_client.get("/v1/mcp/servers")
    assert r.status_code == 503
