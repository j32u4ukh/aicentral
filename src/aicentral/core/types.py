"""aicentral 共用型別。"""

from __future__ import annotations

from typing import Literal, TypedDict

Role = Literal["system", "user", "assistant"]


class Message(TypedDict):
    role: Role
    content: str


class ChatResponse(TypedDict, total=False):
    """非串流回應（可選型別，供日後擴充）。"""

    content: str
    model: str
