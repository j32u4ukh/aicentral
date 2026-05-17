"""
aicentral 主入口：complete()、complete_structured()。

v2.0：經 routing/parser 與 providers/registry 分派。
v3.0：結構化輸出（Instructor-lite）；單次呼叫，重試由消費方負責。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any, Literal, TypeVar, overload

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from aicentral.config import get_config
from aicentral.core.dev import dev_print_exception, is_dev_mode
from aicentral.core.errors import (
    ProviderError,
    StructuredNoPayloadError,
    StructuredValidationError,
)
from aicentral.core.types import Message
from aicentral.routing.router import complete_with_fallback, invoke_resolved, resolve_fallback_chain
from aicentral.structured.debug import summarize_assistant_message
from aicentral.structured.extract import ExtractMode, from_chat_completion
from aicentral.structured.prompt import with_structured_hint
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

    未傳 model 時依 ``AICENTRAL_DEFAULT_MODEL`` → yaml ``defaults.model``
    → ``ollama/{OLLAMA_MODEL}``（見 ``routing.effective_model``）。
    """
    try:
        resolved_messages = _with_system_prompt(messages, system)
        extra = dict(kwargs)
        if base_url is not None:
            extra["base_url"] = base_url
        if api_key is not None:
            extra["api_key"] = api_key
        if stream:
            return complete_with_fallback(
                resolved_messages,
                model,
                stream=True,
                **extra,
            )
        return complete_with_fallback(
            resolved_messages,
            model,
            stream=False,
            **extra,
        )
    except ValueError as exc:
        err = ProviderError(str(exc))
        dev_print_exception(err, context="complete() model 解析失敗")
        raise err from exc
    except ProviderError as exc:
        dev_print_exception(exc, context="complete() 失敗")
        raise


def _guard_structured_kwargs(kwargs: dict[str, Any], *, structured_mode: ExtractMode) -> None:
    if kwargs.pop("stream", None):
        raise ValueError("complete_structured 不支援 stream=True")
    if kwargs.pop("max_retries", None) is not None:
        raise ValueError(
            "complete_structured 已移除 max_retries；請在消費方自行重試，"
            "可搭配 aicentral.structured.retry.append_retry_hint"
        )
    if structured_mode == "tool" and ("tools" in kwargs or "tool_choice" in kwargs):
        raise ValueError("tools 與 tool_choice 由 complete_structured 管理，請勿覆寫")


def _resolve_structured_mode(mode: Literal["tool", "json"]) -> ExtractMode:
    if mode == "json":
        return "json"
    env = os.getenv("AICENTRAL_STRUCTURED_MODE", "tool").strip().lower()
    return "json" if env == "json" else "tool"


def complete_structured(
    messages: list[Message],
    response_model: type[T],
    model: str | None = None,
    *,
    system: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    mode: Literal["tool", "json"] = "tool",
    **kwargs: Any,
) -> T:
    """
    送出對話並回傳通過 Pydantic 驗證的結構化實例（**單次** HTTP 呼叫）。

    失敗時拋出 ``StructuredNoPayloadError`` 或 ``StructuredValidationError``。
    需重試時請由消費方迴圈，並可選用 ``structured.retry.append_retry_hint`` 附加修正提示。

    不提供 ``stream`` 參數（v3.0 刻意不實作結構化串流）。
    """
    structured_mode = _resolve_structured_mode(mode)
    extra = dict(kwargs)
    _guard_structured_kwargs(extra, structured_mode=structured_mode)

    tool_spec = build_tool(response_model) if structured_mode == "tool" else None
    resolved_messages = with_structured_hint(
        _with_system_prompt(messages, system),
        mode=structured_mode,
    )

    cfg = get_config()
    chain = resolve_fallback_chain(model, config=cfg)
    attempted: list[str] = []
    last_exc: ProviderError | None = None
    raw: dict[str, Any] | None = None

    for i, resolved in enumerate(chain):
        attempted.append(resolved.model_label)
        call_extra: dict[str, Any] = {
            "base_url": base_url,
            "api_key": api_key,
            **extra,
        }
        if structured_mode == "json":
            call_extra.setdefault("response_format", {"type": "json_object"})
        if structured_mode == "tool" and tool_spec is not None:
            call_extra["tools"] = tool_spec.tools
            call_extra["tool_choice"] = tool_spec.tool_choice
        try:
            raw = invoke_resolved(
                resolved,
                resolved_messages,
                raw=True,
                **call_extra,
            )
            assert isinstance(raw, dict)
            break
        except ProviderError as exc:
            last_exc = exc
            if exc.is_fallback_eligible(cfg.router.fallback_on) and i < len(chain) - 1:
                continue
            dev_print_exception(exc, context="Provider 連線或 HTTP 錯誤")
            exc.add_note(f"已嘗試 model: {', '.join(attempted)}")
            raise

    if raw is None:
        assert last_exc is not None
        raise last_exc

    summary = summarize_assistant_message(raw)
    payload = from_chat_completion(raw, mode=structured_mode)
    if payload is None:
        detail = (
            "模型未回傳可解析的結構化內容"
            f"（mode={structured_mode}；預期 "
            f"{'tool_calls' if structured_mode == 'tool' else 'content 內 JSON'}）"
        )
        error = StructuredNoPayloadError(
            detail,
            response_model=response_model,
            assistant_summary=summary,
            structured_mode=structured_mode,
        )
        if is_dev_mode():
            dev_print_exception(error, context="結構化：無法解析模型回覆")
        raise error

    try:
        return parse(payload, response_model)
    except ValidationError as exc:
        detail = format_validation_errors(exc)
        error = StructuredValidationError(
            f"結構化驗證失敗: {detail}",
            response_model=response_model,
            validation_detail=detail,
            assistant_summary=summary,
            structured_mode=structured_mode,
        )
        if is_dev_mode():
            dev_print_exception(error, context="結構化：驗證失敗")
        raise error
