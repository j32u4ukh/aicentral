"""結構化請求用的 system 提示補強。"""

from __future__ import annotations

from typing import Literal

from aicentral.core.types import Message

_TOOL_HINT = "請透過提供的 function 工具輸出結構化結果，arguments 必須為合法 JSON。"
_JSON_HINT = (
    "請僅輸出單一 JSON 物件，符合使用者要求的欄位，"
    "不要使用 markdown 程式碼區塊或其它說明。"
)


def with_structured_hint(
    messages: list[Message],
    *,
    mode: Literal["tool", "json"],
) -> list[Message]:
    """在既有 system 訊息末尾追加結構化指示（若無 system 則插入一則）。"""
    hint = _TOOL_HINT if mode == "tool" else _JSON_HINT
    result = list(messages)
    for index, message in enumerate(result):
        if message.get("role") == "system":
            content = str(message.get("content", "")).strip()
            merged = f"{content}\n\n{hint}" if content else hint
            result[index] = {"role": "system", "content": merged}
            return result
    return [{"role": "system", "content": hint}, *result]
