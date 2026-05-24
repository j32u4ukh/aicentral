"""Google Gemini generateContent provider。"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

import httpx

from aicentral.core.errors import ProviderError
from aicentral.core.types import Message
from aicentral.providers.transform.gemini import (
    raw_to_openai_shape,
    text_from_gemini_response,
    to_gemini_request,
)
from aicentral.providers.transform.gemini_tools import apply_openai_tools_to_gemini_payload
from aicentral.routing.gemini_headers import parse_rate_limit_from_response

DEFAULT_TIMEOUT = 120.0
_DEFAULT_BASE = "https://generativelanguage.googleapis.com/v1beta"
_GOOG_API_KEY_HEADER = "X-Goog-Api-Key"

_GEMINI_POOL_KEY = "_gemini_pool"
_GEMINI_MODEL_ID_KEY = "_gemini_model_id"
_OPENAI_ONLY_EXTRA_KEYS = frozenset({"tools", "tool_choice"})


def _normalize_base(base_url: str) -> str:
    return base_url.rstrip("/")


def _pop_internal_extra(extra: dict[str, Any]) -> tuple[Any | None, str | None]:
    pool = extra.pop(_GEMINI_POOL_KEY, None)
    model_id = extra.pop(_GEMINI_MODEL_ID_KEY, None)
    mid = str(model_id).strip() if model_id else None
    return pool, mid


def _build_gemini_payload(
    *,
    messages: list[Message],
    extra: dict[str, Any],
) -> dict[str, Any]:
    """組 Gemini generateContent body；將 OpenAI tools 轉為 functionDeclarations。"""
    call_extra = dict(extra)
    tools = call_extra.pop("tools", None)
    tool_choice = call_extra.pop("tool_choice", None)
    for key in list(call_extra):
        if key in _OPENAI_ONLY_EXTRA_KEYS:
            call_extra.pop(key, None)

    system_instruction, contents = to_gemini_request(messages)
    payload: dict[str, Any] = {"contents": contents, **call_extra}
    if system_instruction:
        payload["systemInstruction"] = system_instruction
    if isinstance(tools, list) and tools:
        apply_openai_tools_to_gemini_payload(payload, tools, tool_choice)
    return payload


def _raise_provider(exc: httpx.RequestError, endpoint: str) -> None:
    if isinstance(exc, httpx.TimeoutException):
        raise ProviderError(f"Gemini 請求逾時: {endpoint}", failure_kind="timeout") from exc
    raise ProviderError(
        f"無法連線至 Gemini {endpoint}: {exc}",
        failure_kind="connection_error",
    ) from exc


def _headers_mapping(response: httpx.Response) -> dict[str, str]:
    return {k: v for k, v in response.headers.items()}


def build_generate_content_url(
    model: str,
    *,
    base_url: str | None = None,
) -> str:
    """
    組出 Google AI Studio ``generateContent`` URL。

    範例：``.../v1beta/models/gemini-3.5-flash:generateContent``
    （模型名稱由 ``model`` / 池輪換的 ``model_id`` 決定）
    """
    base = _normalize_base(base_url or _DEFAULT_BASE)
    model_id = model.strip()
    if not model_id:
        raise ProviderError("Gemini model 名稱不可為空")
    return f"{base}/models/{model_id}:generateContent"


def _request_headers(api_key: str) -> dict[str, str]:
    """Google 建議以 ``X-Goog-Api-Key`` 傳遞 API Key（亦可使用 ``?key=``，本專案採 Header）。"""
    return {
        "Content-Type": "application/json",
        _GOOG_API_KEY_HEADER: api_key,
    }


def _notify_pool(
    pool: Any,
    model_id: str | None,
    headers: Mapping[str, str],
    *,
    status_code: int,
    body: str,
) -> None:
    if pool is None or not model_id:
        return
    pool.apply_headers(model_id, headers, status_code=status_code, body=body)


def _post_generate_content(
    *,
    endpoint: str,
    payload: dict[str, Any],
    api_key: str,
    timeout: float,
    pool: Any | None = None,
    notify_model_id: str | None = None,
) -> httpx.Response:
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                endpoint,
                json=payload,
                headers=_request_headers(api_key),
            )
    except httpx.RequestError as exc:
        _raise_provider(exc, endpoint)

    headers = _headers_mapping(response)
    body_text = response.text if response.status_code >= 400 else ""

    if response.status_code < 400:
        # 方案三：成功回應依 Header 同步（可能偏低，若仍 429 由 apply_headers 上調至官方滿額）
        _notify_pool(pool, notify_model_id, headers, status_code=response.status_code, body="")
        return response

    rate_info = parse_rate_limit_from_response(
        headers, status_code=response.status_code, body=body_text
    )
    # 429：先通知池上調本地計數（官方/Header/自訂上限取 max），再拋錯供 router 換模型
    _notify_pool(
        pool,
        notify_model_id,
        headers,
        status_code=response.status_code,
        body=body_text,
    )
    detail = body_text.strip() or response.reason_phrase
    failure_kind = "rate_limit" if response.status_code == 429 else "http"
    raise ProviderError(
        f"Gemini 回傳錯誤 {response.status_code}: {detail}",
        status_code=response.status_code,
        failure_kind=failure_kind,
        retry_after_seconds=rate_info.retry_after_seconds,
    )


def chat_completions_raw(
    *,
    messages: list[Message],
    model: str,
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    **extra: Any,
) -> dict[str, Any]:
    if not api_key:
        raise ProviderError("Gemini 需要 api_key（設定 GEMINI_API_KEY 或 config）")

    pool, notify_model_id = _pop_internal_extra(extra)
    payload = _build_gemini_payload(messages=messages, extra=extra)

    endpoint = build_generate_content_url(model, base_url=base_url)
    response = _post_generate_content(
        endpoint=endpoint,
        payload=payload,
        api_key=api_key,
        timeout=timeout,
        pool=pool,
        notify_model_id=notify_model_id or model,
    )

    data = response.json()
    if not isinstance(data, dict):
        raise ProviderError(f"無法解析 Gemini 回應: {data!r}")
    return raw_to_openai_shape(data)


def chat_completions(
    *,
    messages: list[Message],
    model: str,
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    **extra: Any,
) -> str:
    if not api_key:
        raise ProviderError("Gemini 需要 api_key（設定 GEMINI_API_KEY 或 config）")

    pool, notify_model_id = _pop_internal_extra(extra)
    payload = _build_gemini_payload(messages=messages, extra=extra)

    endpoint = build_generate_content_url(model, base_url=base_url)
    response = _post_generate_content(
        endpoint=endpoint,
        payload=payload,
        api_key=api_key,
        timeout=timeout,
        pool=pool,
        notify_model_id=notify_model_id or model,
    )

    data = response.json()
    if not isinstance(data, dict):
        raise ProviderError(f"無法解析 Gemini 回應: {data!r}")
    try:
        return text_from_gemini_response(data)
    except KeyError as exc:
        raise ProviderError(f"無法解析 Gemini 回應: {data!r}") from exc


def chat_completions_stream(
    *,
    messages: list[Message],
    model: str,
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    **extra: Any,
) -> Iterator[str]:
    raise ProviderError("Gemini 串流尚未實作（v4.0 P2）")
