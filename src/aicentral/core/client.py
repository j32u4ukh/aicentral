"""
aicentral 主入口：complete()、complete_structured()。

v2.0：經 routing/parser 與 providers/registry 分派。
v3.0：結構化輸出（Instructor-lite）。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any, Literal, TypeVar, overload

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from aicentral.core.errors import ProviderError, StructuredOutputError
from aicentral.core.types import Message
from aicentral.providers.registry import get_provider_module
from aicentral.routing.parser import parse_model
from aicentral.structured.extract import from_chat_completion
from aicentral.structured.retry import append_retry_hint
from aicentral.structured.schema import build_tool
from aicentral.structured.validate import format_validation_errors, parse

load_dotenv()

T = TypeVar("T", bound=BaseModel)

DEFAULT_SYSTEM_PROMPT_ZH_TW = (
    "請一律使用繁體中文（臺灣正體）回覆，用語自然簡潔。若使用者使用其他語言提問，仍以繁體中文回答。"
)


def _with_system_prompt(messages: list[Message], system: str | None) -> list[Message]:
    """若尚無 system 訊息，於開頭插入系統提示（來自參數或 AICENTRAL_SYSTEM_PROMPT）。"""
    if any(m.get("role") == "system" for m in messages):
        return list(messages)

    prompt = system
    if prompt is None:
        prompt = os.getenv("AICENTRAL_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT_ZH_TW)
    if not prompt or not prompt.strip():
        return list(messages)

    return [{"role": "system", "content": prompt.strip()}, *messages]


@overload
def complete(
    messages: list[Message],
    model: str | None = None,
    *,
    stream: bool = False,
    system: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    **kwargs: Any,
) -> str: ...


@overload
def complete(
    messages: list[Message],
    model: str | None = None,
    *,
    stream: bool = True,
    system: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    **kwargs: Any,
) -> Iterator[str]: ...


def complete(
    messages: list[Message],
    model: str | None = None,
    *,
    stream: bool = False,
    system: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    **kwargs: Any,
) -> str | Iterator[str]:
    """
    送出對話並回傳助理回覆。

    model 可為裸名 ``gemma4:e2b`` 或 ``ollama/gemma4:e2b``（v2.0 路由）。
    """
    try:
        parsed = parse_model(model)
    except ValueError as exc:
        raise ProviderError(str(exc)) from exc

    resolved_messages = _with_system_prompt(messages, system)
    provider = get_provider_module(parsed.provider)
    provider_kwargs = {
        "messages": resolved_messages,
        "model": parsed.model_id,
        "base_url": base_url,
        "api_key": api_key,
        **kwargs,
    }

    if stream:
        return provider.chat_completions_stream(**provider_kwargs)
    return provider.chat_completions(**provider_kwargs)


def _structured_max_retries(max_retries: int | None) -> int:
    if max_retries is not None:
        return max(0, max_retries)
    return max(0, int(os.getenv("AICENTRAL_STRUCTURED_MAX_RETRIES", "2")))


def _guard_structured_kwargs(kwargs: dict[str, Any]) -> None:
    if kwargs.pop("stream", None):
        raise ValueError("complete_structured 不支援 stream=True")
    if "tools" in kwargs or "tool_choice" in kwargs:
        raise ValueError("tools 與 tool_choice 由 complete_structured 管理，請勿覆寫")


def complete_structured(
    messages: list[Message],
    response_model: type[T],
    model: str | None = None,
    *,
    max_retries: int | None = None,
    system: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    mode: Literal["tool", "json"] = "tool",
    **kwargs: Any,
) -> T:
    """
    送出對話並回傳通過 Pydantic 驗證的結構化實例。

    使用 OpenAI 相容 ``tools`` / ``tool_calls`` 主路徑；驗證失敗時可重試。
    不提供 ``stream`` 參數（v3.0 刻意不實作結構化串流）。
    """
    if mode != "tool":
        raise ValueError("complete_structured 目前僅支援 mode='tool'（json fallback 為 P2）")

    extra = dict(kwargs)
    _guard_structured_kwargs(extra)
    retries = _structured_max_retries(max_retries)
    total_attempts = retries + 1

    try:
        parsed = parse_model(model)
    except ValueError as exc:
        raise ProviderError(str(exc)) from exc

    tool_spec = build_tool(response_model)
    resolved_messages = _with_system_prompt(messages, system)
    attempt_messages = list(resolved_messages)
    last_error: str | None = None

    provider = get_provider_module(parsed.provider)
    provider_kwargs_base = {
        "base_url": base_url,
        "api_key": api_key,
        **extra,
    }

    for attempt in range(total_attempts):
        raw = provider.chat_completions_raw(
            messages=attempt_messages,
            model=parsed.model_id,
            tools=tool_spec.tools,
            tool_choice=tool_spec.tool_choice,
            **provider_kwargs_base,
        )
        payload = from_chat_completion(raw)
        if payload is None:
            last_error = "模型未回傳 tool_calls 或有效 function.arguments"
            if attempt < retries:
                attempt_messages = append_retry_hint(attempt_messages, last_error)
            continue

        try:
            return parse(payload, response_model)
        except ValidationError as exc:
            last_error = format_validation_errors(exc)
            if attempt < retries:
                attempt_messages = append_retry_hint(attempt_messages, last_error)
            continue

    raise StructuredOutputError(
        f"結構化輸出失敗（已嘗試 {total_attempts} 次）: {last_error or '未知錯誤'}",
        response_model=response_model,
        attempts=total_attempts,
        last_validation_error=last_error,
    )
