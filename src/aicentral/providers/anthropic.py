"""Anthropic Messages API provider。"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx

from aicentral.core.errors import ProviderError
from aicentral.core.types import Message
from aicentral.providers.transform.anthropic import (
    raw_to_openai_shape,
    text_from_anthropic_response,
    to_anthropic_request,
)

DEFAULT_TIMEOUT = 120.0
DEFAULT_MAX_TOKENS = 4096


def _normalize_base(base_url: str) -> str:
    return base_url.rstrip("/")


def _headers(*, api_key: str, api_version: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": api_version,
    }


def _raise_provider(exc: httpx.RequestError, endpoint: str) -> None:
    if isinstance(exc, httpx.TimeoutException):
        raise ProviderError(
            f"Anthropic 請求逾時: {endpoint}",
            failure_kind="timeout",
        ) from exc
    raise ProviderError(
        f"無法連線至 Anthropic {endpoint}: {exc}",
        failure_kind="connection_error",
    ) from exc


def _post_messages(
    *,
    messages: list[Message],
    model: str,
    base_url: str | None,
    api_key: str | None,
    api_version: str | None,
    timeout: float,
    extra: dict[str, Any],
) -> dict[str, Any]:
    if not api_key:
        raise ProviderError("Anthropic 需要 api_key（設定 ANTHROPIC_API_KEY 或 config）")

    base = _normalize_base(base_url or "https://api.anthropic.com")
    version = api_version or "2023-06-01"
    system, anthropic_messages = to_anthropic_request(messages)

    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": extra.pop("max_tokens", DEFAULT_MAX_TOKENS),
        "messages": anthropic_messages,
        **extra,
    }
    if system:
        payload["system"] = system

    endpoint = f"{base}/v1/messages"
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                endpoint,
                json=payload,
                headers=_headers(api_key=api_key, api_version=version),
            )
    except httpx.RequestError as exc:
        _raise_provider(exc, endpoint)

    if response.status_code >= 400:
        detail = response.text.strip() or response.reason_phrase
        raise ProviderError(
            f"Anthropic 回傳錯誤 {response.status_code}: {detail}",
            status_code=response.status_code,
            failure_kind="http",
        )

    data = response.json()
    if not isinstance(data, dict):
        raise ProviderError(f"無法解析 Anthropic 回應: {data!r}")
    return data


def chat_completions_raw(
    *,
    messages: list[Message],
    model: str,
    base_url: str | None = None,
    api_key: str | None = None,
    api_version: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    **extra: Any,
) -> dict[str, Any]:
    native = _post_messages(
        messages=messages,
        model=model,
        base_url=base_url,
        api_key=api_key,
        api_version=api_version,
        timeout=timeout,
        extra=dict(extra),
    )
    return raw_to_openai_shape(native)


def chat_completions(
    *,
    messages: list[Message],
    model: str,
    base_url: str | None = None,
    api_key: str | None = None,
    api_version: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    **extra: Any,
) -> str:
    data = _post_messages(
        messages=messages,
        model=model,
        base_url=base_url,
        api_key=api_key,
        api_version=api_version,
        timeout=timeout,
        extra=dict(extra),
    )
    try:
        return text_from_anthropic_response(data)
    except KeyError as exc:
        raise ProviderError(f"無法解析 Anthropic 回應: {data!r}") from exc


def chat_completions_stream(
    *,
    messages: list[Message],
    model: str,
    base_url: str | None = None,
    api_key: str | None = None,
    api_version: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    **extra: Any,
) -> Iterator[str]:
    raise ProviderError("Anthropic 串流尚未實作（v4.0 P2）")
