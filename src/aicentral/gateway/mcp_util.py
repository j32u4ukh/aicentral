"""Gateway MCP 共用：列表遮罩、依賴檢查。"""

from __future__ import annotations

from typing import Any

from aicentral.config import get_config
from aicentral.config.schema import MCPServerEntry
from aicentral.mcp.registry import merge_mcp_servers, registered_mcp_servers


def mcp_dependency_installed() -> bool:
    try:
        import mcp  # noqa: F401
    except ImportError:
        return False
    return True


def entry_to_public(name: str, entry: MCPServerEntry, *, source: str) -> dict[str, Any]:
    """序列化 server 設定；永不包含 ``auth_value``。"""
    data = entry.model_dump(exclude_none=True, exclude={"auth_value"})
    return {"name": name, "source": source, **data}


def list_servers_public() -> list[dict[str, Any]]:
    cfg = get_config()
    runtime = registered_mcp_servers()
    merged = merge_mcp_servers(cfg)
    return [
        entry_to_public(
            name,
            merged[name],
            source="runtime" if name in runtime else "yaml",
        )
        for name in sorted(merged)
    ]


def get_server_public(name: str) -> dict[str, Any] | None:
    cfg = get_config()
    runtime = registered_mcp_servers()
    merged = merge_mcp_servers(cfg)
    entry = merged.get(name)
    if entry is None:
        return None
    source = "runtime" if name in runtime else "yaml"
    return entry_to_public(name, entry, source=source)


def is_runtime_registered(name: str) -> bool:
    return name.strip() in registered_mcp_servers()
