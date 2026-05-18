"""MCP 工具層（v4.0）。"""

from aicentral.config.schema import MCPServerEntry
from aicentral.mcp.manager import AICENTRAL_MCP_PREFIX, MCPError, MCPManager
from aicentral.mcp.registry import (
    clear_mcp_registry,
    register_mcp_server,
    register_mcp_servers,
    registered_mcp_servers,
    unregister_mcp_server,
)

__all__ = [
    "AICENTRAL_MCP_PREFIX",
    "MCPServerEntry",
    "MCPError",
    "MCPManager",
    "clear_mcp_registry",
    "register_mcp_server",
    "register_mcp_servers",
    "registered_mcp_servers",
    "unregister_mcp_server",
]
