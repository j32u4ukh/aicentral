"""
aicentral 主入口：complete()。

參考 LiteLLM completion() 的「統一入口 + 分派 provider」思想；
v0.1 僅分派至 openai_compat（Ollama）。
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

from aicentral.providers.openai_compat import chat_completions
from aicentral.types import Message

# 載入專案根目錄 .env（開發時）
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


def complete(
    messages: list[Message],
    model: str | None = None,
    *,
    system: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    **kwargs: Any,
) -> str:
    """
    送出對話並回傳助理回覆文字。

    Parameters
    ----------
    messages:
        OpenAI 格式的訊息列表，例如 ``[{"role": "user", "content": "你好"}]``。
    model:
        模型名稱；省略時使用環境變數 ``OLLAMA_MODEL``（預設 ``gemma4:e2b``）。
    system:
        系統提示；省略時使用 ``AICENTRAL_SYSTEM_PROMPT``（預設要求繁體中文回覆）。
        傳 ``""`` 可停用自動插入。若 ``messages`` 已含 ``role: system`` 則不覆寫。
    base_url:
        OpenAI 相容 API 根路徑；省略時使用 ``OLLAMA_BASE_URL``。
    api_key:
        Bearer token；省略時使用 ``OLLAMA_API_KEY``。
    **kwargs:
        傳遞給 chat/completions 的額外參數（如 ``temperature``）。
    """
    resolved_model = model or os.getenv("OLLAMA_MODEL", "gemma4:e2b")
    resolved_messages = _with_system_prompt(messages, system)

    return chat_completions(
        messages=resolved_messages,
        model=resolved_model,
        base_url=base_url,
        api_key=api_key,
        **kwargs,
    )
