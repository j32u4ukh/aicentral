"""Gemini function calling 格式轉換測試。"""

import json

from aicentral.providers.transform.gemini import raw_to_openai_shape, to_gemini_request
from aicentral.providers.transform.gemini_tools import (
    THOUGHT_SIGNATURE_SEPARATOR,
    apply_openai_tools_to_gemini_payload,
    gemini_function_calls_to_openai_tool_calls,
    get_dummy_thought_signature,
    get_thought_signature_from_tool_call,
    openai_tools_to_gemini_tools,
    sanitize_json_schema_for_gemini,
)


def test_sanitize_json_schema_strips_additional_properties() -> None:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "value": {
                "type": "string",
                "additional_properties": False,
                "strict": True,
            },
        },
        "$schema": "http://json-schema.org/draft-07/schema#",
    }
    cleaned = sanitize_json_schema_for_gemini(schema)
    assert "additionalProperties" not in cleaned
    assert "additional_properties" not in cleaned["properties"]["value"]
    assert "strict" not in cleaned["properties"]["value"]
    assert "$schema" not in cleaned


def test_openai_tools_to_gemini_function_declarations() -> None:
    openai_tools = [
        {
            "type": "function",
            "function": {
                "name": "Unity_ManageScene",
                "description": "管理場景",
                "parameters": {
                    "type": "object",
                    "additional_properties": False,
                    "properties": {"x": {"type": "string", "additionalProperties": False}},
                },
            },
        }
    ]
    gemini_tools = openai_tools_to_gemini_tools(openai_tools)
    assert len(gemini_tools) == 1
    decls = gemini_tools[0]["functionDeclarations"]
    assert decls[0]["name"] == "Unity_ManageScene"
    assert "additional_properties" not in decls[0]["parameters"]
    assert "additionalProperties" not in decls[0]["parameters"]["properties"]["x"]
    assert "type" not in gemini_tools[0]
    assert "function" not in gemini_tools[0]


def test_apply_openai_tools_to_payload() -> None:
    payload: dict = {"contents": []}
    apply_openai_tools_to_gemini_payload(
        payload,
        [{"type": "function", "function": {"name": "foo", "parameters": {}}}],
        "auto",
    )
    assert "functionDeclarations" in payload["tools"][0]
    assert payload["toolConfig"]["functionCallingConfig"]["mode"] == "AUTO"


def test_to_gemini_request_tool_roundtrip() -> None:
    messages = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call_0",
                    "type": "function",
                    "function": {
                        "name": "Unity_ListResources",
                        "arguments": "{}",
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_0",
            "content": json.dumps({"ok": True}),
        },
    ]
    _, contents = to_gemini_request(messages)
    assert contents[1]["role"] == "model"
    fc_part = contents[1]["parts"][0]
    assert "functionCall" in fc_part
    assert fc_part.get("thoughtSignature") == get_dummy_thought_signature()
    assert contents[2]["parts"][0]["functionResponse"]["name"] == "Unity_ListResources"


def test_thought_signature_roundtrip() -> None:
    sig = "dGVzdF9zaWc="
    parts = [
        {
            "functionCall": {"name": "unity__Unity_ManageScene", "args": {"action": "create"}},
            "thoughtSignature": sig,
        }
    ]
    tool_calls = gemini_function_calls_to_openai_tool_calls(parts)
    assert THOUGHT_SIGNATURE_SEPARATOR in tool_calls[0]["id"]
    assert tool_calls[0]["provider_specific_fields"]["thought_signature"] == sig
    assert get_thought_signature_from_tool_call(tool_calls[0]) == sig

    _, contents = to_gemini_request(
        [
            {"role": "user", "content": "go"},
            {"role": "assistant", "tool_calls": tool_calls},
            {
                "role": "tool",
                "tool_call_id": tool_calls[0]["id"],
                "content": "{}",
            },
        ]
    )
    model_part = contents[1]["parts"][0]
    assert model_part["thoughtSignature"] == sig


def test_raw_to_openai_shape_function_call() -> None:
    sig = "YWJjZGVm"
    data = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "functionCall": {
                                "name": "Unity_ManageGameObject",
                                "args": {"action": "create"},
                            },
                            "thoughtSignature": sig,
                        }
                    ]
                }
            }
        ]
    }
    shaped = raw_to_openai_shape(data)
    msg = shaped["choices"][0]["message"]
    assert msg["tool_calls"][0]["function"]["name"] == "Unity_ManageGameObject"
    assert msg["tool_calls"][0]["provider_specific_fields"]["thought_signature"] == sig
    assert sig in msg["tool_calls"][0]["id"]
    assert json.loads(msg["tool_calls"][0]["function"]["arguments"]) == {
        "action": "create"
    }
