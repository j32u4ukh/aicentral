"""
aicentral 主入口：complete()。

v2.0：經 routing/parser 與 providers/registry 分派。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any, overload

from dotenv import load_dotenv

from aicentral.core.errors import ProviderError
from aicentral.core.types import Message
from aicentral.providers.registry import get_provider_module
from aicentral.routing.parser import parse_model

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
