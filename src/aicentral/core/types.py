"""aicentral 共用型別。"""

from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

Role = Literal["system", "user", "assistant", "tool"]

# 純文字或 OpenAI 多模態 parts（text / image_url）
MessageContent = str | list[dict[str, Any]]


class Message(TypedDict):
    """對話訊息；tool / assistant+tool_calls 欄位供 MCP 編排使用。"""

    role: Role
    content: NotRequired[MessageContent]
    tool_calls: NotRequired[list[dict[str, Any]]]
    tool_call_id: NotRequired[str]
    name: NotRequired[str]


class ChatResponse(TypedDict, total=False):
    """非串流回應（可選型別，供日後擴充）。"""

    content: str
    model: str


def user_message(content: str) -> Message:
    """將使用者問題轉成單則 ``user`` 訊息（供 ``complete`` / ``Chat`` 使用）。"""
    return {"role": "user", "content": content}


def as_messages(messages: str | list[Message]) -> list[Message]:
    """字串視為單則 user 訊息；已是列表則複製回傳。"""
    if isinstance(messages, str):
        return [user_message(messages)]
    return list(messages)
