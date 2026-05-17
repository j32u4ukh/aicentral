"""aicentral 共用型別。"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

Role = Literal["system", "user", "assistant"]

# 純文字或 OpenAI 多模態 parts（text / image_url）
MessageContent = str | list[dict[str, Any]]


class Message(TypedDict):
    role: Role
    content: MessageContent


class ChatResponse(TypedDict, total=False):
    """非串流回應（可選型別，供日後擴充）。"""

    content: str
    model: str
