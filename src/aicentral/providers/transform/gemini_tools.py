"""OpenAI Chat Completions tools ↔ Gemini generateContent function calling。

參考 LiteLLM ``llms/gemini`` 與 Google REST ``functionDeclarations`` / ``functionCall`` 規範；
MCP 編排層仍使用 OpenAI 形狀，僅在 ``providers/gemini`` 發送前後轉換。
"""

from __future__ import annotations

import base64
import copy
import json
from typing import Any

# Gemini 3+ 多輪 function calling 需在 functionCall part 帶回 thoughtSignature
# https://ai.google.dev/gemini-api/docs/thought-signatures
THOUGHT_SIGNATURE_SEPARATOR = "__thought__"

# Gemini functionDeclarations.parameters 接受的 OpenAPI Schema 子集（參考 LiteLLM vertex_ai.Schema）
_GEMINI_SCHEMA_ALLOWLIST = frozenset(
    {
        "type",
        "format",
        "title",
        "description",
        "nullable",
        "default",
        "items",
        "minItems",
        "maxItems",
        "enum",
        "properties",
        "propertyOrdering",
        "required",
        "minProperties",
        "maxProperties",
        "minimum",
        "maximum",
        "minLength",
        "maxLength",
        "pattern",
        "example",
        "anyOf",
    }
)

# OpenAI / Pydantic / MCP 常見但 Gemini 不接受的欄位（含 snake_case）
_GEMINI_SCHEMA_STRIP_KEYS = frozenset(
    {
        "additionalProperties",
        "additional_properties",
        "strict",
        "$schema",
        "$id",
        "$defs",
        "definitions",
        "$ref",
    }
)


def sanitize_json_schema_for_gemini(schema: Any) -> Any:
    """
    遞迴清理 JSON Schema，供 Gemini ``functionDeclarations.parameters`` 使用。

    LiteLLM 在 ``_map_function`` 會呼叫 ``_remove_additional_properties`` 與
    ``_build_vertex_schema``；MCP 工具 schema 常含 ``additional_properties``（snake_case）
    或 ``additionalProperties: false``，直接送出會 400。
    """
    if isinstance(schema, dict):
        cleaned: dict[str, Any] = {}
        for key, value in schema.items():
            if key in _GEMINI_SCHEMA_STRIP_KEYS:
                continue
            if key not in _GEMINI_SCHEMA_ALLOWLIST:
                continue
            if key == "properties" and isinstance(value, dict):
                cleaned[key] = {
                    prop: sanitize_json_schema_for_gemini(prop_schema)
                    for prop, prop_schema in value.items()
                }
            elif key == "items" and isinstance(value, dict):
                cleaned[key] = sanitize_json_schema_for_gemini(value)
            elif key == "anyOf" and isinstance(value, list):
                cleaned[key] = [
                    sanitize_json_schema_for_gemini(item)
                    for item in value
                    if isinstance(item, (dict, list))
                ]
            else:
                cleaned[key] = value
        return cleaned
    if isinstance(schema, list):
        return [sanitize_json_schema_for_gemini(item) for item in schema]
    return schema


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
        decl["parameters"] = sanitize_json_schema_for_gemini(copy.deepcopy(params))
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


def get_dummy_thought_signature() -> str:
    """Gemini 3 驗證用占位簽名（Google 文件建議）。"""
    return base64.b64encode(b"skip_thought_signature_validator").decode("utf-8")


def encode_tool_call_id_with_signature(
    tool_call_id: str,
    thought_signature: str | None,
) -> str:
    if thought_signature:
        return f"{tool_call_id}{THOUGHT_SIGNATURE_SEPARATOR}{thought_signature}"
    return tool_call_id


def strip_thought_from_tool_call_id(tool_call_id: str) -> str:
    return tool_call_id.split(THOUGHT_SIGNATURE_SEPARATOR, 1)[0]


def get_thought_signature_from_tool_call(
    tool_call: dict[str, Any],
    *,
    use_dummy_if_missing: bool = False,
) -> str | None:
    """
    從 OpenAI ``tool_calls`` 項目還原 Gemini ``thoughtSignature``。

    來源順序：``provider_specific_fields`` → 嵌於 ``id`` 的字串 → dummy（可選）。
    """
    psf = tool_call.get("provider_specific_fields")
    if isinstance(psf, dict):
        sig = psf.get("thought_signature") or psf.get("thoughtSignature")
        if sig:
            return str(sig)

    fn = tool_call.get("function")
    if isinstance(fn, dict):
        fn_psf = fn.get("provider_specific_fields")
        if isinstance(fn_psf, dict):
            sig = fn_psf.get("thought_signature") or fn_psf.get("thoughtSignature")
            if sig:
                return str(sig)

    tc_id = tool_call.get("id")
    if isinstance(tc_id, str) and THOUGHT_SIGNATURE_SEPARATOR in tc_id:
        parts = tc_id.split(THOUGHT_SIGNATURE_SEPARATOR, 1)
        if len(parts) == 2 and parts[1]:
            return parts[1]

    if use_dummy_if_missing:
        return get_dummy_thought_signature()
    return None


def openai_tool_call_to_gemini_part(
    tool_call: dict[str, Any],
    *,
    use_dummy_thought_signature: bool = True,
) -> dict[str, Any]:
    """OpenAI ``tool_calls[]`` 單項 → Gemini ``parts[]`` 元素（含 ``functionCall``）。"""
    fn = tool_call.get("function")
    if not isinstance(fn, dict):
        raise ValueError(f"tool_call 缺少 function: {tool_call!r}")
    name = str(fn.get("name", ""))
    args = _parse_function_arguments(fn.get("arguments"))
    part: dict[str, Any] = {"functionCall": {"name": name, "args": args}}
    sig = get_thought_signature_from_tool_call(
        tool_call,
        use_dummy_if_missing=use_dummy_thought_signature,
    )
    if sig:
        part["thoughtSignature"] = sig
    return part


def register_tool_call_name(
    mapping: dict[str, str],
    tool_call_id: Any,
    name: str,
) -> None:
    """登錄 tool_call_id（含 thought 後綴）→ function name，供 ``role: tool`` 對照。"""
    if not name:
        return
    raw = str(tool_call_id)
    mapping[raw] = name
    clean = strip_thought_from_tool_call_id(raw)
    if clean != raw:
        mapping[clean] = name


def resolve_tool_call_name(mapping: dict[str, str], tool_call_id: str) -> str | None:
    return mapping.get(tool_call_id) or mapping.get(
        strip_thought_from_tool_call_id(tool_call_id)
    )


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
        thought_sig = part.get("thoughtSignature") or part.get("thought_signature")
        call_id = f"call_{idx}"
        tc: dict[str, Any] = {
            "id": call_id,
            "type": "function",
            "function": {
                "name": name,
                "arguments": json.dumps(args, ensure_ascii=False),
            },
        }
        if thought_sig:
            sig_str = str(thought_sig)
            tc["id"] = encode_tool_call_id_with_signature(call_id, sig_str)
            tc["provider_specific_fields"] = {"thought_signature": sig_str}
        tool_calls.append(tc)
    return tool_calls
