"""結構化重試用的訊息組裝。"""

from __future__ import annotations

from aicentral.core.types import Message

_RETRY_PREFIX = (
    "上一輪輸出未通過驗證，請修正後僅呼叫工具 function。\n錯誤："
)


def append_retry_hint(messages: list[Message], error_summary: str) -> list[Message]:
    """在訊息列表末尾追加一則 user 修正提示。"""
    hint: Message = {
        "role": "user",
        "content": f"{_RETRY_PREFIX}{error_summary}",
    }
    return [*messages, hint]
