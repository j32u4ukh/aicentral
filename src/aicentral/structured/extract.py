"""從 chat/completions 回應抽取 JSON 物件。"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

ExtractMode = Literal["tool", "json"]


def from_chat_completion(
    data: dict[str, Any],
    *,
    mode: ExtractMode = "tool",
) -> dict[str, Any] | None:
    """
    自 OpenAI 相容回應取出結構化 payload。

    - ``tool``：``tool_calls[0].function.arguments``
    - ``json``：``message.content`` 內 JSON（可選再 fallback tool_calls）
    """
    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return None

    if mode == "json":
        payload = from_message_content(message)
        if payload is not None:
            return payload
        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list) and tool_calls:
            return _arguments_from_tool_call(tool_calls[0])
        return None

    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list) and tool_calls:
        return _arguments_from_tool_call(tool_calls[0])
    return None


def from_message_content(message: dict[str, Any]) -> dict[str, Any] | None:
    """從 assistant ``content`` 解析 JSON 物件（``mode=json``）。"""
    content = message.get("content")
    if not isinstance(content, str):
        return None
    text = _strip_json_fence(content.strip())
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _strip_json_fence(text: str) -> str:
    """移除 ```json ... ``` 包裹。"""
    match = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text


def _arguments_from_tool_call(tool_call: Any) -> dict[str, Any] | None:
    if not isinstance(tool_call, dict):
        return None
    function = tool_call.get("function")
    if not isinstance(function, dict):
        return None
    arguments = function.get("arguments")
    if arguments is None:
        return None
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        text = arguments.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None
