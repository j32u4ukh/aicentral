"""
OpenAI Chat Completions 相容 HTTP 適配器。

v0.1 用於 Ollama（/v1/chat/completions）；v0.4 可共用於其他 OpenAI 相容端點。
參考：LiteLLM 對 OpenAI chat 端點的呼叫方式；Ollama OpenAI 相容文件。
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from aicentral.exceptions import ProviderError
from aicentral.types import Message

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
    """
    呼叫 OpenAI 相容的 chat/completions，回傳助理文字內容。

    extra 可傳 temperature 等 OpenAI 參數（Ollama 支援的子集）。
    """
    url_base = _normalize_base_url(
        base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    )
    key = api_key if api_key is not None else os.getenv("OLLAMA_API_KEY", "ollama")

    # TODO: 定義數據結構的類別, 並使用 Pydantic 進行驗證
    payload: dict[str, Any] = {
        "model": model,
        "messages": to_openai_messages(messages),
        **extra,
    }

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    endpoint = f"{url_base}/chat/completions"

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
