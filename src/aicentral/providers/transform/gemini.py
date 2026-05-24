"""OpenAI 風格 Message[] ↔ Gemini generateContent。"""

from __future__ import annotations

import json
from typing import Any

from aicentral.core.types import Message
from aicentral.providers.transform.gemini_tools import gemini_function_calls_to_openai_tool_calls


def to_gemini_request(
    messages: list[Message],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """
    回傳 (system_instruction, contents)。

    支援 assistant ``tool_calls`` 與 ``role: tool``（對應 Gemini functionCall / functionResponse）。
    """
    system_parts: list[str] = []
    contents: list[dict[str, Any]] = []
    tool_call_id_to_name: dict[str, str] = {}

    for msg in messages:
        role = msg.get("role", "user")
        if role == "system":
            content = str(msg.get("content", ""))
            if content:
                system_parts.append(content)
            continue

        if role == "assistant":
            tool_calls = msg.get("tool_calls")
            parts: list[dict[str, Any]] = []
            text = msg.get("content")
            if text is not None and str(text).strip():
                parts.append({"text": str(text)})
            if isinstance(tool_calls, list):
                for tc in tool_calls:
                    if not isinstance(tc, dict):
                        continue
                    fn = tc.get("function")
                    if not isinstance(fn, dict):
                        continue
                    name = str(fn.get("name", ""))
                    tc_id = tc.get("id")
                    if tc_id is not None and name:
                        tool_call_id_to_name[str(tc_id)] = name
                    args = _parse_function_arguments(fn.get("arguments"))
                    parts.append({"functionCall": {"name": name, "args": args}})
            if parts:
                contents.append({"role": "model", "parts": parts})
            continue

        if role == "tool":
            tc_id = str(msg.get("tool_call_id", ""))
            name = tool_call_id_to_name.get(tc_id)
            if not name:
                # 無對照時略過文字化，避免 Gemini 400
                content = str(msg.get("content", ""))
                if content.strip():
                    contents.append(
                        {
                            "role": "user",
                            "parts": [{"text": content}],
                        }
                    )
                continue
            response_obj = _tool_content_to_response_object(msg.get("content"))
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": name,
                                "response": response_obj,
                            }
                        }
                    ],
                }
            )
            continue

        gemini_role = "model" if role == "assistant" else "user"
        content = str(msg.get("content", ""))
        if content or role == "user":
            contents.append(
                {
                    "role": gemini_role,
                    "parts": [{"text": content}] if content else [{"text": ""}],
                }
            )

    system_instruction: dict[str, Any] | None = None
    if system_parts:
        system_instruction = {"parts": [{"text": "\n\n".join(system_parts)}]}
    return system_instruction, contents


def _parse_function_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except json.JSONDecodeError:
            return {"raw": raw}
    return {}


def _tool_content_to_response_object(content: Any) -> dict[str, Any]:
    if content is None:
        return {}
    if isinstance(content, dict):
        return content
    text = str(content)
    if not text.strip():
        return {}
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        return {"result": parsed}
    except json.JSONDecodeError:
        return {"result": text}


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
    """將 Gemini 回應包成 OpenAI chat completion 形狀（含 functionCall → tool_calls）。"""
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise KeyError("candidates")
    content = candidates[0].get("content", {})
    parts = content.get("parts", [])
    if not isinstance(parts, list):
        parts = []

    tool_calls = gemini_function_calls_to_openai_tool_calls(parts)
    texts: list[str] = []
    for part in parts:
        if isinstance(part, dict) and "text" in part:
            texts.append(str(part["text"]))

    message: dict[str, Any] = {
        "role": "assistant",
        "content": "".join(texts) if texts else None,
    }
    if tool_calls:
        message["tool_calls"] = tool_calls
        if message["content"] is None:
            message["content"] = None

    if not tool_calls and not texts:
        # 無文字也無工具呼叫時 fallback（維持舊行為拋錯由呼叫方處理）
        text = text_from_gemini_response(data)
        message["content"] = text

    return {
        "choices": [
            {
                "message": message,
            }
        ]
    }
