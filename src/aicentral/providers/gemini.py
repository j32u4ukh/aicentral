"""Google Gemini generateContent provider。"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx

from aicentral.core.errors import ProviderError
from aicentral.core.types import Message
from aicentral.providers.transform.gemini import (
    raw_to_openai_shape,
    text_from_gemini_response,
    to_gemini_request,
)

DEFAULT_TIMEOUT = 120.0


def _normalize_base(base_url: str) -> str:
    return base_url.rstrip("/")


def _raise_provider(exc: httpx.RequestError, endpoint: str) -> None:
    if isinstance(exc, httpx.TimeoutException):
        raise ProviderError(f"Gemini 請求逾時: {endpoint}", failure_kind="timeout") from exc
    raise ProviderError(
        f"無法連線至 Gemini {endpoint}: {exc}",
        failure_kind="connection_error",
    ) from exc


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

    base = _normalize_base(
        base_url or "https://generativelanguage.googleapis.com/v1beta"
    )
    system_instruction, contents = to_gemini_request(messages)

    payload: dict[str, Any] = {"contents": contents, **extra}
    if system_instruction:
        payload["systemInstruction"] = system_instruction

    endpoint = f"{base}/models/{model}:generateContent"
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(endpoint, json=payload, params={"key": api_key})
    except httpx.RequestError as exc:
        _raise_provider(exc, endpoint)

    if response.status_code >= 400:
        detail = response.text.strip() or response.reason_phrase
        raise ProviderError(
            f"Gemini 回傳錯誤 {response.status_code}: {detail}",
            status_code=response.status_code,
            failure_kind="http",
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
    base = _normalize_base(
        base_url or "https://generativelanguage.googleapis.com/v1beta"
    )
    if not api_key:
        raise ProviderError("Gemini 需要 api_key（設定 GEMINI_API_KEY 或 config）")

    system_instruction, contents = to_gemini_request(messages)
    payload: dict[str, Any] = {"contents": contents, **extra}
    if system_instruction:
        payload["systemInstruction"] = system_instruction

    endpoint = f"{base}/models/{model}:generateContent"
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(endpoint, json=payload, params={"key": api_key})
    except httpx.RequestError as exc:
        _raise_provider(exc, endpoint)

    if response.status_code >= 400:
        detail = response.text.strip() or response.reason_phrase
        raise ProviderError(
            f"Gemini 回傳錯誤 {response.status_code}: {detail}",
            status_code=response.status_code,
            failure_kind="http",
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
