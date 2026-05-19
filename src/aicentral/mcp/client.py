"""MCP 連線（stdio / http / sse），依賴官方 ``mcp`` 套件。"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

from aicentral.config.schema import MCPServerEntry

_MCP_IMPORT_ERROR = (
    "MCP 功能需要安裝 mcp 套件：pip install 'aicentral[mcp]' 或 pip install mcp>=1.6.0"
)


def _require_mcp() -> Any:
    try:
        import mcp  # noqa: F401
    except ImportError as exc:
        raise ImportError(_MCP_IMPORT_ERROR) from exc
    return mcp


@asynccontextmanager
async def mcp_session(entry: MCPServerEntry, *, timeout: float):
    """建立 MCP ClientSession（依 transport）。"""
    _require_mcp()
    from mcp.client.sse import sse_client
    from mcp.client.stdio import stdio_client

    from mcp import ClientSession, StdioServerParameters

    transport = entry.transport
    if transport == "stdio":
        if not entry.command:
            raise ValueError("stdio transport 需要 command")
        params = StdioServerParameters(
            command=entry.command,
            args=entry.args,
            env=entry.env or None,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=timeout)
                yield session
    elif transport == "sse":
        if not entry.url:
            raise ValueError("sse transport 需要 url")
        headers = _auth_headers(entry)
        async with sse_client(entry.url, headers=headers) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=timeout)
                yield session
    elif transport == "http":
        if not entry.url:
            raise ValueError("http transport 需要 url")
        try:
            import mcp.client.streamable_http as streamable_http_module
        except ImportError as exc:
            raise ImportError(
                f"{_MCP_IMPORT_ERROR}（此 transport 需 mcp 的 streamable_http 支援）"
            ) from exc
        client = getattr(streamable_http_module, "streamable_http_client", None)
        if client is None:
            raise ImportError("mcp 版本不支援 streamable_http_client")
        from mcp.shared._httpx_utils import create_mcp_http_client

        headers = _auth_headers(entry) or None
        async with create_mcp_http_client(headers) as http_client:
            async with client(entry.url, http_client=http_client) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await asyncio.wait_for(session.initialize(), timeout=timeout)
                    yield session
    else:
        raise ValueError(f"不支援的 MCP transport: {transport}")


def _auth_headers(entry: MCPServerEntry) -> dict[str, str]:
    headers = dict(entry.static_headers)
    auth = entry.auth_type
    value = entry.auth_value
    if not value or auth == "none":
        return headers
    if auth == "bearer_token":
        headers["Authorization"] = f"Bearer {value}"
    elif auth in ("api_key", "authorization"):
        headers["Authorization"] = value
    elif auth == "basic":
        import base64

        encoded = base64.b64encode(value.encode()).decode()
        headers["Authorization"] = f"Basic {encoded}"
    return headers


async def alist_tools(entry: MCPServerEntry, *, timeout: float) -> list[dict[str, Any]]:
    async with mcp_session(entry, timeout=timeout) as session:
        result = await session.list_tools()
        tools: list[dict[str, Any]] = []
        for tool in result.tools:
            tools.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.inputSchema,
                }
            )
        return tools


async def acall_tool(
    entry: MCPServerEntry,
    name: str,
    arguments: dict[str, Any],
    *,
    timeout: float,
) -> Any:
    from mcp.types import CallToolRequestParams

    async with mcp_session(entry, timeout=timeout) as session:
        params = CallToolRequestParams(name=name, arguments=arguments)
        return await session.call_tool(params.name, params.arguments)
