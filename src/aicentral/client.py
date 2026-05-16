"""
aicentral 主入口：complete()。

參考 LiteLLM completion() 的「統一入口 + 分派 provider」思想；
v0.1 僅分派至 openai_compat（Ollama）。
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

from aicentral.providers.openai_compat import Message, chat_completions

# 載入專案根目錄 .env（開發時）
load_dotenv()


def complete(
    messages: list[Message],
    model: str | None = None,
    *,
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
        模型名稱；省略時使用環境變數 ``OLLAMA_MODEL``（預設 ``llama3.2``）。
    base_url:
        OpenAI 相容 API 根路徑；省略時使用 ``OLLAMA_BASE_URL``。
    api_key:
        Bearer token；省略時使用 ``OLLAMA_API_KEY``。
    **kwargs:
        傳遞給 chat/completions 的額外參數（如 ``temperature``）。
    """
    resolved_model = model or os.getenv("OLLAMA_MODEL", "llama3.2")

    return chat_completions(
        messages=messages,
        model=resolved_model,
        base_url=base_url,
        api_key=api_key,
        **kwargs,
    )
