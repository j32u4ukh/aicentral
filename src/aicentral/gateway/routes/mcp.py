"""MCP HTTP 路由（v0.6.1）：執行期 server 列表 + list_tools / call_tool。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse, Response

from aicentral.gateway.auth import verify_optional_bearer
from aicentral.gateway.errors import mcp_error_response, openai_error_response
from aicentral.gateway.mcp_util import (
    get_server_public,
    is_runtime_registered,
    list_servers_public,
    mcp_dependency_installed,
)
from aicentral.gateway.schemas import (
    MCPServerListResponse,
    MCPServerRegisterBody,
    MCPToolCallBody,
    MCPToolCallResponse,
    MCPToolsListResponse,
)
from aicentral.mcp.manager import MCPError, MCPManager
from aicentral.mcp.orchestrator import serialize_tool_result
from aicentral.mcp.registry import register_mcp_server, register_mcp_servers, unregister_mcp_server

router = APIRouter()


def _ensure_mcp() -> None:
    if not mcp_dependency_installed():
        raise ImportError(
            "MCP 路由需要安裝 mcp 套件：pip install 'aicentral[gateway,mcp]'"
        )


@router.get("/v1/mcp/servers", response_model=MCPServerListResponse)
def list_mcp_servers(_: None = Depends(verify_optional_bearer)) -> MCPServerListResponse:
    try:
        _ensure_mcp()
        return MCPServerListResponse(servers=list_servers_public())
    except ImportError as exc:
        return mcp_error_response(exc, status_code=503)  # type: ignore[return-value]


@router.get("/v1/mcp/servers/{server}")
def get_mcp_server(server: str, _: None = Depends(verify_optional_bearer)):
    try:
        _ensure_mcp()
        item = get_server_public(server)
        if item is None:
            return openai_error_response(f"未知 MCP server: {server!r}", status_code=404)
        return JSONResponse(content=item)
    except ImportError as exc:
        return mcp_error_response(exc, status_code=503)


@router.post("/v1/mcp/servers")
def register_mcp_servers_route(
    body: dict[str, Any] = Body(...),
    _: None = Depends(verify_optional_bearer),
):
    try:
        _ensure_mcp()
        if "servers" in body and isinstance(body["servers"], dict):
            names = list(body["servers"].keys())
            any_runtime = any(is_runtime_registered(n) for n in names)
            register_mcp_servers(body["servers"])
            status = 200 if any_runtime else 201
            return JSONResponse(
                status_code=status,
                content={"registered": names},
            )
        try:
            reg = MCPServerRegisterBody.model_validate(body)
        except Exception as exc:
            return openai_error_response(f"無效的 server 設定: {exc}", status_code=400)
        existed = is_runtime_registered(reg.name)
        register_mcp_server(reg.name, reg.to_entry())
        status = 200 if existed else 201
        return JSONResponse(status_code=status, content={"name": reg.name, "registered": True})
    except ImportError as exc:
        return mcp_error_response(exc, status_code=503)
    except ValueError as exc:
        return openai_error_response(str(exc), status_code=400)


@router.put("/v1/mcp/servers/{server}")
def put_mcp_server(
    server: str,
    body: dict[str, Any] = Body(...),
    _: None = Depends(verify_optional_bearer),
):
    try:
        _ensure_mcp()
        payload = dict(body)
        payload["name"] = server
        try:
            reg = MCPServerRegisterBody.model_validate(payload)
        except Exception as exc:
            return openai_error_response(f"無效的 server 設定: {exc}", status_code=400)
        if reg.name != server:
            return openai_error_response("路徑 server 與 body.name 不一致", status_code=400)
        register_mcp_server(server, reg.to_entry())
        return JSONResponse(content={"name": server, "registered": True})
    except ImportError as exc:
        return mcp_error_response(exc, status_code=503)
    except ValueError as exc:
        return openai_error_response(str(exc), status_code=400)


@router.delete("/v1/mcp/servers/{server}")
def delete_mcp_server(server: str, _: None = Depends(verify_optional_bearer)):
    try:
        _ensure_mcp()
        if not is_runtime_registered(server):
            if get_server_public(server) is not None:
                return openai_error_response(
                    f"server {server!r} 僅定義於 yaml，無法以 HTTP 刪除執行期註冊",
                    status_code=404,
                )
            return openai_error_response(f"未知 MCP server: {server!r}", status_code=404)
        unregister_mcp_server(server)
        return Response(status_code=204)
    except ImportError as exc:
        return mcp_error_response(exc, status_code=503)


@router.get("/v1/mcp/{server}/tools", response_model=MCPToolsListResponse)
def list_mcp_tools(server: str, _: None = Depends(verify_optional_bearer)):
    try:
        _ensure_mcp()
        mgr = MCPManager.from_config()
        tools = mgr.list_tools(server)
        return MCPToolsListResponse(tools=tools)
    except ImportError as exc:
        return mcp_error_response(exc, status_code=503)  # type: ignore[return-value]
    except MCPError as exc:
        return mcp_error_response(exc, status_code=404)  # type: ignore[return-value]


@router.post("/v1/mcp/{server}/tools/{tool_name}", response_model=MCPToolCallResponse)
def call_mcp_tool(
    server: str,
    tool_name: str,
    body: MCPToolCallBody,
    _: None = Depends(verify_optional_bearer),
):
    try:
        _ensure_mcp()
        mgr = MCPManager.from_config()
        raw = mgr.call_tool(server, tool_name, body.arguments)
        return MCPToolCallResponse(result=_json_safe_result(raw))
    except ImportError as exc:
        return mcp_error_response(exc, status_code=503)  # type: ignore[return-value]
    except MCPError as exc:
        return mcp_error_response(exc)  # type: ignore[return-value]


def _json_safe_result(raw: Any) -> Any:
    text = serialize_tool_result(raw)
    try:
        import json

        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text
