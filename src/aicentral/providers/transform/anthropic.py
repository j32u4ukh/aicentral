"""OpenAI 風格 Message[] ↔ Anthropic Messages API。"""

from __future__ import annotations

from typing import Any

from aicentral.core.types import Message


def to_anthropic_request(messages: list[Message]) -> tuple[str | None, list[dict[str, Any]]]:
    """回傳 (system, anthropic_messages)。"""
    system_parts: list[str] = []
    out: list[dict[str, Any]] = []

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            if content:
                system_parts.append(str(content))
            continue
        if role not in ("user", "assistant"):
            role = "user"
        out.append({"role": role, "content": str(content)})

    system = "\n\n".join(system_parts) if system_parts else None
    return system, out


def raw_to_openai_shape(data: dict[str, Any]) -> dict[str, Any]:
    """包成 OpenAI chat completion 形狀（供 structured extract）。"""
    blocks = data.get("content")
    if not isinstance(blocks, list):
        raise KeyError("content")
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for i, block in enumerate(blocks):
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            text_parts.append(str(block.get("text", "")))
        elif block.get("type") == "tool_use":
            tool_calls.append(
                {
                    "id": str(block.get("id", f"call_{i}")),
                    "type": "function",
                    "function": {
                        "name": block.get("name", ""),
                        "arguments": block.get("input", {}),
                    },
                }
            )
    message: dict[str, Any] = {
        "role": "assistant",
        "content": "".join(text_parts) or None,
    }
    if tool_calls:
        import json

        for tc in tool_calls:
            args = tc["function"]["arguments"]
            if not isinstance(args, str):
                tc["function"]["arguments"] = json.dumps(args, ensure_ascii=False)
        message["tool_calls"] = tool_calls
    return {"choices": [{"message": message}]}


def text_from_anthropic_response(data: dict[str, Any]) -> str:
    """從 Messages API 回應取出助理文字。"""
    blocks = data.get("content")
    if not isinstance(blocks, list):
        raise KeyError("content")
    parts: list[str] = []
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if text:
                parts.append(str(text))
    if not parts:
        raise KeyError("text blocks")
    return "".join(parts)
