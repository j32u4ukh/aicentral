"""OpenAI Chat Completions tools ↔ Gemini generateContent function calling。

參考 LiteLLM ``llms/gemini`` 與 Google REST ``functionDeclarations`` / ``functionCall`` 規範；
MCP 編排層仍使用 OpenAI 形狀，僅在 ``providers/gemini`` 發送前後轉換。
"""

from __future__ import annotations

import json
from typing import Any


def openai_tool_entry_to_declaration(entry: dict[str, Any]) -> dict[str, Any]:
    """單一 OpenAI ``{type, function}`` → Gemini ``FunctionDeclaration``。"""
    fn = entry.get("function")
    if not isinstance(fn, dict):
        fn = entry
    name = str(fn.get("name", "")).strip()
    if not name:
        raise ValueError(f"工具缺少 name: {entry!r}")
    decl: dict[str, Any] = {"name": name}
    if fn.get("description"):
        decl["description"] = str(fn["description"])
    params = fn.get("parameters")
    if isinstance(params, dict) and params:
        decl["parameters"] = params
    return decl


def openai_tools_to_gemini_tools(openai_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    OpenAI ``tools`` 陣列 → Gemini ``tools``（含 ``functionDeclarations``）。

    Gemini 不接受頂層 ``type`` / ``function`` 欄位。
    """
    if not openai_tools:
        return []
    declarations: list[dict[str, Any]] = []
    for entry in openai_tools:
        if not isinstance(entry, dict):
            continue
        declarations.append(openai_tool_entry_to_declaration(entry))
    if not declarations:
        return []
    return [{"functionDeclarations": declarations}]


def openai_tool_choice_to_gemini_tool_config(
    tool_choice: Any,
) -> dict[str, Any] | None:
    """OpenAI ``tool_choice`` → Gemini ``toolConfig.functionCallingConfig``。"""
    if tool_choice is None:
        return None
    if tool_choice == "none":
        return {"functionCallingConfig": {"mode": "NONE"}}
    if tool_choice in ("auto", "required"):
        mode = "ANY" if tool_choice == "required" else "AUTO"
        return {"functionCallingConfig": {"mode": mode}}
    if isinstance(tool_choice, dict):
        fn = tool_choice.get("function")
        if isinstance(fn, dict) and fn.get("name"):
            return {
                "functionCallingConfig": {
                    "mode": "ANY",
                    "allowedFunctionNames": [str(fn["name"])],
                }
            }
    return {"functionCallingConfig": {"mode": "AUTO"}}


def apply_openai_tools_to_gemini_payload(
    payload: dict[str, Any],
    openai_tools: list[dict[str, Any]] | None,
    tool_choice: Any = None,
) -> None:
    """將 OpenAI tools / tool_choice 寫入 Gemini payload（就地修改）。"""
    if openai_tools:
        gemini_tools = openai_tools_to_gemini_tools(openai_tools)
        if gemini_tools:
            payload["tools"] = gemini_tools
    tool_config = openai_tool_choice_to_gemini_tool_config(tool_choice)
    if tool_config is not None:
        payload["toolConfig"] = tool_config


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


def gemini_function_calls_to_openai_tool_calls(
    parts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Gemini ``parts`` 內的 ``functionCall`` → OpenAI ``tool_calls``。"""
    tool_calls: list[dict[str, Any]] = []
    for idx, part in enumerate(parts):
        if not isinstance(part, dict):
            continue
        fc = part.get("functionCall")
        if not isinstance(fc, dict):
            continue
        name = str(fc.get("name", ""))
        args = fc.get("args", fc.get("arguments", {}))
        tool_calls.append(
            {
                "id": f"call_{idx}",
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(args, ensure_ascii=False),
                },
            }
        )
    return tool_calls
