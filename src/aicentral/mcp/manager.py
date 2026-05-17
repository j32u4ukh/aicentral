"""MCP server 管理（對照 LiteLLM proxy mcp_servers）。"""

from __future__ import annotations

import asyncio
from typing import Any

from aicentral.config import get_config, load_config
from aicentral.config.schema import AICentralConfig, MCPServerEntry
from aicentral.mcp.client import acall_tool, alist_tools

AICENTRAL_MCP_PREFIX = "aicentral/mcp/"


class MCPError(Exception):
    """MCP 操作失敗。"""


class MCPManager:
    """依設定檔管理多個 MCP server。"""

    def __init__(self, config: AICentralConfig) -> None:
        self._config = config

    @classmethod
    def from_config(cls, *, path: str | None = None) -> MCPManager:
        cfg = load_config(path=path) if path else get_config()
        return cls(cfg)

    def _get_entry(self, server_name: str) -> MCPServerEntry:
        allowed = self._config.mcp_settings.allowed_servers
        if allowed is not None and server_name not in allowed:
            raise MCPError(f"MCP server 不在白名單: {server_name!r}")
        entry = self._config.mcp_servers.get(server_name)
        if entry is None:
            known = ", ".join(sorted(self._config.mcp_servers))
            raise MCPError(f"未知 MCP server: {server_name!r}（已定義: {known or '無'}）")
        return entry

    def _timeout(self, entry: MCPServerEntry) -> float:
        return entry.timeout or self._config.mcp_settings.client_timeout

    def _prefixed_name(self, server_name: str, tool_name: str) -> str:
        if self._config.mcp_settings.tool_name_prefix:
            return f"{server_name}__{tool_name}"
        return tool_name

    def list_tools(self, server_name: str) -> list[dict[str, Any]]:
        entry = self._get_entry(server_name)
        tools = asyncio.run(alist_tools(entry, timeout=self._timeout(entry)))
        return [
            {
                **t,
                "name": self._prefixed_name(server_name, t["name"]),
                "mcp_server": server_name,
            }
            for t in self._filter_tools(entry, tools)
        ]

    def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        entry = self._get_entry(server_name)
        bare_name = tool_name
        prefix = f"{server_name}__"
        if tool_name.startswith(prefix):
            bare_name = tool_name[len(prefix) :]
        if entry.allowed_tools and bare_name not in entry.allowed_tools:
            raise MCPError(f"工具不在白名單: {bare_name!r}")
        if entry.disallowed_tools and bare_name in entry.disallowed_tools:
            raise MCPError(f"工具已禁用: {bare_name!r}")
        return asyncio.run(
            acall_tool(
                entry,
                bare_name,
                arguments or {},
                timeout=self._timeout(entry),
            )
        )

    def list_all_tools(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for name in self._config.mcp_servers:
            if self._config.mcp_settings.allowed_servers is None or name in (
                self._config.mcp_settings.allowed_servers
            ):
                out.extend(self.list_tools(name))
        return out

    @staticmethod
    def parse_server_url(server_url: str) -> str | None:
        """解析 ``aicentral/mcp/<name>`` 為 server_name。"""
        if server_url.startswith(AICENTRAL_MCP_PREFIX):
            return server_url[len(AICENTRAL_MCP_PREFIX) :].strip("/") or None
        return None

    def _filter_tools(
        self, entry: MCPServerEntry, tools: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for t in tools:
            name = t.get("name", "")
            if entry.allowed_tools and name not in entry.allowed_tools:
                continue
            if entry.disallowed_tools and name in entry.disallowed_tools:
                continue
            out.append(t)
        return out
