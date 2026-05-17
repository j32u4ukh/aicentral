"""請求 body 大小限制。"""

from __future__ import annotations

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response


class MaxBodyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, *, max_bytes: int) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._max_bytes = max_bytes

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method in ("POST", "PUT", "PATCH"):
            content_length = request.headers.get("content-length")
            if content_length is not None:
                try:
                    if int(content_length) > self._max_bytes:
                        return JSONResponse(
                            status_code=413,
                            content={
                                "error": {
                                    "message": "Request body too large",
                                    "type": "invalid_request_error",
                                    "code": None,
                                }
                            },
                        )
                except ValueError:
                    pass
        return await call_next(request)
