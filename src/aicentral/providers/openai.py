"""
OpenAI Chat Completions 相容 HTTP 適配器。

v2.0：由 openai_compat 遷入；用於 Ollama 等 OpenAI 相容端點。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import httpx

from aicentral.core.errors import ProviderError
from aicentral.core.types import Message
from aicentral.providers.streaming import extract_delta_content, parse_sse_data_line

DEFAULT_TIMEOUT = 120.0


def to_openai_messages(messages: list[Message]) -> list[dict[str, Any]]:
    """將 aicentral Message 轉為 OpenAI chat/completions 的 messages 陣列。"""
    return [{"role": m["role"], "content": m["content"]} for m in messages]


def _normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def chat_completions(
    *,
    messages: list[Message],
    model: str,
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    **extra: Any,
) -> str:
    """呼叫 OpenAI 相容的 chat/completions，回傳助理文字內容。"""
    endpoint, headers, payload = _build_request(
        messages=messages,
        model=model,
        base_url=base_url,
        api_key=api_key,
        stream=False,
        extra=extra,
    )

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(endpoint, json=payload, headers=headers)
    except httpx.RequestError as exc:
        raise ProviderError(f"無法連線至 LLM 端點 {endpoint}: {exc}") from exc

    if response.status_code >= 400:
        detail = response.text.strip() or response.reason_phrase
        raise ProviderError(
            f"LLM 端點回傳錯誤 {response.status_code}: {detail}",
            status_code=response.status_code,
        )

    data = response.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError(f"無法解析 LLM 回應: {data!r}") from exc
    if content is None:
        raise ProviderError(f"LLM 回應 content 為空: {data!r}")
    return str(content)


def _build_request(
    *,
    messages: list[Message],
    model: str,
    base_url: str | None,
    api_key: str | None,
    stream: bool,
    extra: dict[str, Any],
) -> tuple[str, dict[str, str], dict[str, Any]]:
    url_base = _normalize_base_url(
        base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    )
    key = api_key if api_key is not None else os.getenv("OLLAMA_API_KEY", "ollama")
    payload: dict[str, Any] = {
        "model": model,
        "messages": to_openai_messages(messages),
        "stream": stream,
        **extra,
    }
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return f"{url_base}/chat/completions", headers, payload


def chat_completions_stream(
    *,
    messages: list[Message],
    model: str,
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    **extra: Any,
) -> Iterator[str]:
    """串流呼叫 chat/completions，逐段 yield 助理文字增量。"""
    endpoint, headers, payload = _build_request(
        messages=messages,
        model=model,
        base_url=base_url,
        api_key=api_key,
        stream=True,
        extra=extra,
    )

    try:
        with httpx.Client(timeout=timeout) as client:
            with client.stream("POST", endpoint, json=payload, headers=headers) as response:
                if response.status_code >= 400:
                    body = response.read().decode(errors="replace").strip()
                    detail = body or response.reason_phrase
                    raise ProviderError(
                        f"LLM 端點回傳錯誤 {response.status_code}: {detail}",
                        status_code=response.status_code,
                    )
                for line in response.iter_lines():
                    chunk = parse_sse_data_line(line)
                    if chunk is None:
                        continue
                    delta = extract_delta_content(chunk)
                    if delta is not None:
                        yield delta
    except ProviderError:
        raise
    except httpx.RequestError as exc:
        raise ProviderError(f"無法連線至 LLM 端點 {endpoint}: {exc}") from exc
