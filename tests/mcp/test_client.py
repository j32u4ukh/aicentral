"""MCP client transport 單元測試。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aicentral.config.schema import MCPServerEntry
from aicentral.mcp.client import mcp_session


@asynccontextmanager
async def _fake_create_mcp_http_client(headers=None):
    client = MagicMock()
    client.headers = headers or {}
    yield client


@pytest.mark.asyncio
async def test_http_transport_passes_http_client() -> None:
    """streamable_http_client 新版以 http_client 帶 headers，不接受 headers=。"""
    entry = MCPServerEntry(
        transport="http",
        url="https://example.com/mcp",
        auth_type="bearer_token",
        auth_value="tok",
    )
    mock_session = MagicMock()
    mock_session.initialize = AsyncMock()
    captured: dict = {}

    @asynccontextmanager
    async def fake_streamable(url: str, *, http_client=None, terminate_on_close=True):
        captured["url"] = url
        captured["http_client"] = http_client
        yield (MagicMock(), MagicMock(), lambda: None)

    @asynccontextmanager
    async def fake_client_session(read, write):
        yield mock_session

    with (
        patch(
            "mcp.shared._httpx_utils.create_mcp_http_client",
            _fake_create_mcp_http_client,
        ),
        patch(
            "mcp.client.streamable_http.streamable_http_client",
            fake_streamable,
        ),
        patch("mcp.ClientSession", fake_client_session),
    ):
        async with mcp_session(entry, timeout=5.0) as session:
            assert session is mock_session

    assert captured["url"] == entry.url
    assert captured["http_client"].headers["Authorization"] == "Bearer tok"
    mock_session.initialize.assert_awaited_once()
