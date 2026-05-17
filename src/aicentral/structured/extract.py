"""從 chat/completions 回應抽取 JSON 物件。"""

from __future__ import annotations

import json
from typing import Any


def from_chat_completion(data: dict[str, Any]) -> dict[str, Any] | None:
    """
    自 OpenAI 相容回應取出結構化 payload。

    優先 ``choices[0].message.tool_calls[0].function.arguments``（JSON 字串）。
    """
    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return None

    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list) and tool_calls:
        return _arguments_from_tool_call(tool_calls[0])

    return None


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
