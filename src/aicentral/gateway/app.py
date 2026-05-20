"""FastAPI Gateway 應用。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from aicentral.config import load_config
from aicentral.config.loader import get_config
from aicentral.gateway.localhost import LocalClientMiddleware
from aicentral.gateway.middleware import MaxBodyMiddleware
from aicentral.gateway.routes import chat, health, mcp


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield


def create_app() -> FastAPI:
    cfg = get_config().gateway

    app = FastAPI(title="aicentral Gateway", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(mcp.router)

    app.add_middleware(
        MaxBodyMiddleware,
        max_bytes=cfg.max_body_bytes,
    )
    app.add_middleware(
        LocalClientMiddleware,
        enabled=cfg.reject_non_local_client,
    )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        _request: Request, exc: HTTPException
    ) -> JSONResponse:
        if isinstance(exc.detail, dict):
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "message": str(exc.detail),
                    "type": "invalid_request_error",
                    "code": None,
                }
            },
        )

    return app


app = create_app()
