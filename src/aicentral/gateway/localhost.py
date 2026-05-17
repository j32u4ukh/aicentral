"""本機 loopback 綁定與客戶端 IP 檢查。"""

from __future__ import annotations

import ipaddress

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
# Starlette TestClient 的 client.host 為 "testclient"
_LOOPBACK_CLIENTS = _LOOPBACK_HOSTS | frozenset({"testclient"})


def is_loopback_host(host: str) -> bool:
    h = host.strip().lower()
    if h in _LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


def validate_bind_host(bind_host: str) -> str:
    """僅允許 loopback；否則拋 ValueError。"""
    host = bind_host.strip()
    if not is_loopback_host(host):
        raise ValueError(
            f"gateway.bind_host 必須為 loopback（127.0.0.1 或 ::1），目前為: {bind_host!r}"
        )
    return host


def is_loopback_client(host: str | None) -> bool:
    if not host:
        return False
    h = host.strip().lower()
    if h in _LOOPBACK_CLIENTS:
        return True
    return is_loopback_host(host)


class LocalClientMiddleware(BaseHTTPMiddleware):
    """拒絕非本機 client（依 ``request.client.host``）。"""

    def __init__(self, app: object, *, enabled: bool = True) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._enabled = enabled

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if self._enabled and request.url.path != "/health":
            client = request.client.host if request.client else None
            if not is_loopback_client(client):
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": {
                            "message": "僅允許本機連線",
                            "type": "access_denied",
                            "code": None,
                        }
                    },
                )
        return await call_next(request)
