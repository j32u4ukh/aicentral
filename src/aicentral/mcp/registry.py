"""執行期註冊 MCP server（與 yaml ``mcp_servers`` 合併）。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aicentral.config.schema import AICentralConfig, MCPServerEntry

_REGISTRY: dict[str, MCPServerEntry] = {}


def register_mcp_server(
    name: str,
    entry: MCPServerEntry | None = None,
    /,
    **kwargs: Any,
) -> None:
    """註冊單一 MCP server，供 ``MCPManager`` 與 yaml 設定合併使用。

    ``entry`` 與 ``**kwargs`` 二擇一；``kwargs`` 會傳入 ``MCPServerEntry``。
    同名稱再次註冊會覆寫先前項目（亦覆寫 yaml 中同名 server）。
    """
    key = name.strip()
    if not key:
        raise ValueError("MCP server 名稱不可為空")
    if entry is not None and kwargs:
        raise ValueError("請只傳 entry 或關鍵字參數，不可同時傳入")
    if entry is None:
        entry = MCPServerEntry(**kwargs)
    _REGISTRY[key] = entry


def register_mcp_servers(
    servers: Mapping[str, MCPServerEntry | dict[str, Any]],
) -> None:
    """批次註冊 MCP server。"""
    for name, value in servers.items():
        if isinstance(value, MCPServerEntry):
            register_mcp_server(name, value)
        else:
            register_mcp_server(name, MCPServerEntry.model_validate(value))


def unregister_mcp_server(name: str) -> None:
    """移除執行期註冊的 server（不影響 yaml）。"""
    _REGISTRY.pop(name.strip(), None)


def clear_mcp_registry() -> None:
    """清空執行期註冊表（主要供測試）。"""
    _REGISTRY.clear()


def registered_mcp_servers() -> dict[str, MCPServerEntry]:
    """目前執行期註冊的 server 副本。"""
    return dict(_REGISTRY)


def merge_mcp_servers(
    config: AICentralConfig,
    *,
    extra: Mapping[str, MCPServerEntry] | None = None,
) -> dict[str, MCPServerEntry]:
    """合併 yaml、全域註冊表與可選的實例級 ``extra``（後者優先）。"""
    merged = dict(config.mcp_servers)
    merged.update(_REGISTRY)
    if extra:
        merged.update(extra)
    return merged
