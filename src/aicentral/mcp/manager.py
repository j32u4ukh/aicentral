"""MCP server 管理（對照 LiteLLM proxy mcp_servers）。

MCP 與 Cursor SKILL 的分工
--------------------------
- **MCP 工具**：各 MCP server 透過協定 ``list_tools`` 回傳 ``name``、``description``、
  ``inputSchema``（JSON Schema）。模型在收到 tools 清單後，依這些欄位決定何時呼叫、
  要傳哪些參數——**不必**在 aicentral 另寫類似 SKILL.md 的「用法說明檔」。
- **本模組**：只負責讀 yaml 連線設定、白名單、工具名稱前綴，並代為連線
  ``list_tools`` / ``call_tool``；**不**定義各工具的語意（語意由 MCP server 提供）。
- **仍須設定**：``config/aicentral.yaml`` 的 ``mcp_servers``（URL、transport、認證等）
  告訴程式「連哪個 server」，這與工具自我說明是兩件事。
- **尚未自動**：0.5.0 不會在 ``complete()`` 內自動跑「模型 ↔ 工具」迴圈；應用層需
  自行 ``list_tools`` → 把結果塞進 ``tools`` → 模型選工具 → ``call_tool``（見 0.6 規劃）。
"""

from __future__ import annotations

import asyncio
from typing import Any

from aicentral.config import get_config, load_config
from aicentral.config.schema import AICentralConfig, MCPServerEntry
from aicentral.mcp.client import acall_tool, alist_tools

# 設定或 OpenAI tools 內可用的內部別名，對應 yaml 的 server 名稱
AICENTRAL_MCP_PREFIX = "aicentral/mcp/"


class MCPError(Exception):
    """MCP 操作失敗（未知 server、白名單、工具禁用等）；不觸發 LLM provider fallback。"""


class MCPManager:
    """依設定檔管理多個 MCP server 的連線與工具列舉／執行。

    工具的中繼資料（description、inputSchema）來自遠端 server 的 ``list_tools``，
    經 ``list_tools`` / ``list_all_tools`` 原樣（加上可選名稱前綴）交給呼叫方或 LLM。
    """

    def __init__(self, config: AICentralConfig) -> None:
        self._config = config

    @classmethod
    def from_config(cls, *, path: str | None = None) -> MCPManager:
        """從 yaml 建立實例；``path`` 為 None 時使用已載入的 ``get_config()``。"""
        cfg = load_config(path=path) if path else get_config()
        return cls(cfg)

    def _get_entry(self, server_name: str) -> MCPServerEntry:
        """解析 server 名稱並套用 ``mcp_settings.allowed_servers`` 全域白名單。"""
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
        """多 server 時加 ``server__tool`` 前綴，避免不同 server 工具同名衝突。"""
        if self._config.mcp_settings.tool_name_prefix:
            return f"{server_name}__{tool_name}"
        return tool_name

    def list_tools(self, server_name: str) -> list[dict[str, Any]]:
        """向指定 MCP server 取得工具清單。

        每筆 dict 含 server 回傳的 ``name``、``description``、``inputSchema``，
        以及 ``mcp_server``；``description`` / ``inputSchema`` 即工具「自我說明」，
        供模型或應用層轉成 OpenAI ``tools`` 格式，無需另寫 SKILL 類文件。
        """
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
        """執行工具；``tool_name`` 可為帶前綴的 ``server__bare`` 或裸名。"""
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
        """彙總所有已設定（且通過全域白名單）server 的工具。"""
        out: list[dict[str, Any]] = []
        for name in self._config.mcp_servers:
            if self._config.mcp_settings.allowed_servers is None or name in (
                self._config.mcp_settings.allowed_servers
            ):
                out.extend(self.list_tools(name))
        return out

    @staticmethod
    def parse_server_url(server_url: str) -> str | None:
        """解析 ``aicentral/mcp/<name>`` 為 yaml 中的 ``server_name``。"""
        if server_url.startswith(AICENTRAL_MCP_PREFIX):
            return server_url[len(AICENTRAL_MCP_PREFIX) :].strip("/") or None
        return None

    def _filter_tools(
        self, entry: MCPServerEntry, tools: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """依單一 server 的 ``allowed_tools`` / ``disallowed_tools`` 過濾（連線後才套用）。"""
        out: list[dict[str, Any]] = []
        for t in tools:
            name = t.get("name", "")
            if entry.allowed_tools and name not in entry.allowed_tools:
                continue
            if entry.disallowed_tools and name in entry.disallowed_tools:
                continue
            out.append(t)
        return out
