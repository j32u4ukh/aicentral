"""Pydantic 驗證與錯誤訊息格式化。"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


def parse(data: dict[str, object], response_model: type[T]) -> T:
    """驗證並回傳 model 實例。"""
    return response_model.model_validate(data)


def format_validation_errors(exc: ValidationError) -> str:
    """將 ValidationError 轉成可餵回模型的短訊息。"""
    parts: list[str] = []
    for error in exc.errors():
        loc = ".".join(str(item) for item in error.get("loc", ()))
        msg = error.get("msg", "invalid")
        if loc:
            parts.append(f"{loc}: {msg}")
        else:
            parts.append(str(msg))
    return "; ".join(parts) if parts else str(exc)
