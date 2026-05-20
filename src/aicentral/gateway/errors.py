"""Gateway OpenAI 相容錯誤回應。"""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse


def openai_error_response(
    message: str,
    *,
    status_code: int,
    error_type: str = "invalid_request_error",
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"message": message, "type": error_type, "code": None}},
    )


def mcp_error_response(exc: Exception, *, status_code: int = 400) -> JSONResponse:
    from aicentral.mcp.manager import MCPError

    if isinstance(exc, MCPError):
        return openai_error_response(str(exc), status_code=status_code, error_type="mcp_error")
    if isinstance(exc, ImportError):
        return openai_error_response(str(exc), status_code=503, error_type="api_error")
    return openai_error_response(str(exc), status_code=status_code)


def provider_error_response(exc: Exception) -> JSONResponse:
    from aicentral.core.errors import ProviderError

    if isinstance(exc, ProviderError):
        if exc.failure_kind == "timeout":
            return openai_error_response(str(exc), status_code=504, error_type="timeout_error")
        if exc.failure_kind == "connection_error":
            return openai_error_response(str(exc), status_code=502, error_type="api_error")
        if exc.status_code == 401:
            return openai_error_response(str(exc), status_code=502, error_type="api_error")
        return openai_error_response(str(exc), status_code=502, error_type="api_error")
    return openai_error_response(str(exc), status_code=500, error_type="api_error")
