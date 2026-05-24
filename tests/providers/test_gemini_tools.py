"""Gemini function calling 格式轉換測試。"""

import json

from aicentral.providers.transform.gemini import raw_to_openai_shape, to_gemini_request
from aicentral.providers.transform.gemini_tools import (
    apply_openai_tools_to_gemini_payload,
    openai_tools_to_gemini_tools,
)


def test_openai_tools_to_gemini_function_declarations() -> None:
    openai_tools = [
        {
            "type": "function",
            "function": {
                "name": "Unity_ManageScene",
                "description": "管理場景",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    gemini_tools = openai_tools_to_gemini_tools(openai_tools)
    assert len(gemini_tools) == 1
    decls = gemini_tools[0]["functionDeclarations"]
    assert decls[0]["name"] == "Unity_ManageScene"
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
    assert "functionCall" in contents[1]["parts"][0]
    assert contents[2]["parts"][0]["functionResponse"]["name"] == "Unity_ListResources"


def test_raw_to_openai_shape_function_call() -> None:
    data = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "functionCall": {
                                "name": "Unity_ManageGameObject",
                                "args": {"action": "create"},
                            }
                        }
                    ]
                }
            }
        ]
    }
    shaped = raw_to_openai_shape(data)
    msg = shaped["choices"][0]["message"]
    assert msg["tool_calls"][0]["function"]["name"] == "Unity_ManageGameObject"
    assert json.loads(msg["tool_calls"][0]["function"]["arguments"]) == {
        "action": "create"
    }
