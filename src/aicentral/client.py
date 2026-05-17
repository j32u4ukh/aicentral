"""
aicentral 主入口：complete()。

參考 LiteLLM completion() 的「統一入口 + 分派 provider」思想；
v1.1 支援 stream=True 串流回應。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any, overload

from dotenv import load_dotenv

from aicentral.providers.openai_compat import chat_completions, chat_completions_stream
from aicentral.types import Message

load_dotenv()

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


def _resolve_model(model: str | None) -> str:
    return model or os.getenv("OLLAMA_MODEL", "gemma4:e2b")


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

    Parameters
    ----------
    messages:
        訊息列表，例如 ``[{"role": "user", "content": "你好"}]``。
    model:
        模型名稱；省略時使用 ``OLLAMA_MODEL``（預設 ``gemma4:e2b``）。
    stream:
        ``False``（預設）回傳完整 ``str``；``True`` 回傳文字增量 ``Iterator[str]``。
    system:
        系統提示；省略時使用 ``AICENTRAL_SYSTEM_PROMPT``。
        傳 ``""`` 可停用自動插入。
    base_url:
        OpenAI 相容 API 根路徑；省略時使用 ``OLLAMA_BASE_URL``。
    api_key:
        Bearer token；省略時使用 ``OLLAMA_API_KEY``。
    **kwargs:
        傳遞給 chat/completions 的額外參數（如 ``temperature``）。
    """
    resolved_model = _resolve_model(model)
    resolved_messages = _with_system_prompt(messages, system)
    provider_kwargs = {
        "messages": resolved_messages,
        "model": resolved_model,
        "base_url": base_url,
        "api_key": api_key,
        **kwargs,
    }

    if stream:
        return chat_completions_stream(**provider_kwargs)
    return chat_completions(**provider_kwargs)
