"""aicentral 共用型別（v1.1）。"""

from __future__ import annotations

from typing import Literal, TypedDict

Role = Literal["system", "user", "assistant"]


class Message(TypedDict):
    role: Role
    content: str
