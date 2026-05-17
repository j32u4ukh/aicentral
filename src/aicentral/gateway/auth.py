"""可選 Bearer token（本機）。"""

from __future__ import annotations

from fastapi import Header

from aicentral.config import get_config


def verify_optional_bearer(authorization: str | None = Header(default=None)) -> None:
    token = get_config().gateway.optional_token
    if not token:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise _auth_error()
    provided = authorization[7:].strip()
    if provided != token:
        raise _auth_error()


def _auth_error() -> Exception:
    from fastapi import HTTPException

    return HTTPException(
        status_code=401,
        detail={
            "error": {
                "message": "Invalid or missing API key",
                "type": "authentication_error",
                "code": None,
            }
        },
    )
