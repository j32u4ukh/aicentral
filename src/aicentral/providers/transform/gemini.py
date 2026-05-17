"""OpenAI 風格 Message[] ↔ Gemini generateContent。"""

from __future__ import annotations

from typing import Any

from aicentral.core.types import Message


def to_gemini_request(
    messages: list[Message],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """回傳 (system_instruction, contents)。"""
    system_parts: list[str] = []
    contents: list[dict[str, Any]] = []

    for msg in messages:
        role = msg.get("role", "user")
        content = str(msg.get("content", ""))
        if role == "system":
            if content:
                system_parts.append(content)
            continue
        gemini_role = "model" if role == "assistant" else "user"
        contents.append(
            {
                "role": gemini_role,
                "parts": [{"text": content}],
            }
        )

    system_instruction: dict[str, Any] | None = None
    if system_parts:
        system_instruction = {"parts": [{"text": "\n\n".join(system_parts)}]}
    return system_instruction, contents


def text_from_gemini_response(data: dict[str, Any]) -> str:
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise KeyError("candidates")
    content = candidates[0].get("content", {})
    parts = content.get("parts", [])
    texts: list[str] = []
    for part in parts:
        if isinstance(part, dict) and "text" in part:
            texts.append(str(part["text"]))
    if not texts:
        raise KeyError("text parts")
    return "".join(texts)


def raw_to_openai_shape(data: dict[str, Any]) -> dict[str, Any]:
    """將 Gemini 回應包成 OpenAI chat completion 形狀（供 structured extract）。"""
    text = text_from_gemini_response(data)
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": text,
                }
            }
        ]
    }
