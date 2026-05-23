"""
aicentral 主入口：complete()、complete_structured()。

v2.0：經 routing/parser 與 providers/registry 分派。
v3.0：結構化輸出（Instructor-lite）；單次呼叫，重試由消費方負責。
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Literal, TypeVar, overload

import httpx
from pydantic import BaseModel, ValidationError

from aicentral.config import get_config
from aicentral.config.loader import get_structured_mode, get_system_prompt
from aicentral.core.dev import dev_print_exception, is_dev_mode
from aicentral.core.errors import (
    ProviderError,
    StructuredNoPayloadError,
    StructuredValidationError,
)
from aicentral.core.types import Message, as_messages
from aicentral.mcp.manager import MCPError
from aicentral.mcp.orchestrator import complete_with_mcp_loop
from aicentral.routing.router import (
    complete_with_fallback,
    invoke_resolved,
    resolve_call,
    resolve_fallback_chain,
)
from aicentral.structured.debug import summarize_assistant_message
from aicentral.structured.extract import ExtractMode, from_chat_completion
from aicentral.structured.prompt import with_structured_hint
from aicentral.structured.schema import build_tool
from aicentral.structured.validate import format_validation_errors, parse

T = TypeVar("T", bound=BaseModel)

DEFAULT_SYSTEM_PROMPT_ZH_TW = (
    "請一律使用繁體中文（臺灣正體）回覆，用語自然簡潔。若使用者使用其他語言提問，仍以繁體中文回答。"
)


def _with_system_prompt(messages: list[Message], system: str | None) -> list[Message]:
    """若尚無 system 訊息，於開頭插入系統提示（參數或 aicentral.yaml）。"""
    if any(m.get("role") == "system" for m in messages):
        return list(messages)

    prompt = system if system is not None else get_system_prompt(DEFAULT_SYSTEM_PROMPT_ZH_TW)
    if not prompt or not prompt.strip():
        return list(messages)

    return [{"role": "system", "content": prompt.strip()}, *messages]


@overload
def complete(
    messages: str | list[Message],
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
    messages: str | list[Message],
    model: str | None = None,
    *,
    stream: bool = True,
    system: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    **kwargs: Any,
) -> Iterator[str]: ...


def complete(
    messages: str | list[Message],
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

  ``messages`` 可為 **使用者問題字串**（自動包成 ``role: user``）或訊息列表。

    model 可為裸名 ``gemma4:e2b`` 或 ``ollama/gemma4:e2b``（v2.0 路由）。

    未傳 model 時依 yaml ``defaults.model``（見 ``routing.effective_model``）。

    ``mcp_servers``：啟用 MCP 工具編排（非串流）；見 ``mcp/orchestrator``。
    有狀態多輪請用 ``Chat.with_mcp(...).ask(...)``。
    """
    try:
        resolved_messages = _with_system_prompt(as_messages(messages), system)
        extra = dict(kwargs)
        mcp_servers = extra.pop("mcp_servers", None)
        max_tool_rounds = int(extra.pop("max_tool_rounds", 5))
        return_message_trail = bool(extra.pop("return_message_trail", False))
        if base_url is not None:
            extra["base_url"] = base_url
        if api_key is not None:
            extra["api_key"] = api_key
        if mcp_servers is not None:
            if stream:
                raise ValueError("mcp_servers 不支援 stream=True；請使用 stream=False")
            return complete_with_mcp_loop(
                resolved_messages,
                model,
                mcp_servers=mcp_servers,
                max_tool_rounds=max_tool_rounds,
                return_message_trail=return_message_trail,
                **extra,
            )
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
    except MCPError:
        raise
    except ValueError as exc:
        msg = str(exc)
        if "mcp_servers" in msg or "max_tool_rounds" in msg or "return_message_trail" in msg:
            raise
        err = ProviderError(msg)
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
    return "json" if get_structured_mode() == "json" else "tool"


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


def _embeddings_endpoint(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/embeddings"
    return f"{base}/v1/embeddings"


def embedding(
    text: str,
    model: str | None = None,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: float | None = None,
    **kwargs: Any,
) -> list[float]:
    """呼叫 OpenAI 相容 ``/v1/embeddings``，回傳向量。"""
    resolved = resolve_call(model)
    endpoint_base = base_url or resolved.base_url
    if not endpoint_base:
        raise ProviderError("embedding 需要 base_url（參數或設定檔）", failure_kind="config")

    key = api_key if api_key is not None else resolved.api_key
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    payload: dict[str, Any] = {
        "model": resolved.model_id,
        "input": text,
        **kwargs,
    }
    endpoint = _embeddings_endpoint(endpoint_base)
    request_timeout = timeout if timeout is not None else resolved.timeout

    try:
        with httpx.Client(timeout=request_timeout) as client:
            response = client.post(endpoint, json=payload, headers=headers)
    except httpx.TimeoutException as exc:
        raise ProviderError(
            f"Embedding 端點請求逾時 {endpoint}: {exc}",
            failure_kind="timeout",
        ) from exc
    except httpx.RequestError as exc:
        raise ProviderError(
            f"無法連線至 Embedding 端點 {endpoint}: {exc}",
            failure_kind="connection_error",
        ) from exc

    if response.status_code >= 400:
        detail = response.text.strip() or response.reason_phrase
        raise ProviderError(
            f"Embedding 端點回傳錯誤 {response.status_code}: {detail}",
            status_code=response.status_code,
            failure_kind="http",
        )

    data = response.json()
    if isinstance(data, dict) and "data" in data:
        items = data["data"]
        if items and isinstance(items[0], dict) and "embedding" in items[0]:
            vec = items[0]["embedding"]
            if isinstance(vec, list):
                return [float(x) for x in vec]
    if isinstance(data, dict) and "embedding" in data:
        vec = data["embedding"]
        if isinstance(vec, list):
            return [float(x) for x in vec]

    raise ProviderError(f"無法解析 Embedding 回應: {data!r}")
