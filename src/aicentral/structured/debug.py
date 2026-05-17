"""結構化路徑的除錯用摘要（開發模式）。"""

from __future__ import annotations

import json
from typing import Any


def summarize_assistant_message(raw: dict[str, Any]) -> str:
    """將 provider 回應中的 assistant 訊息壓成可讀一行摘要。"""
    try:
        message = raw["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return f"無法解析 choices: {json.dumps(raw, ensure_ascii=False)[:400]}"

    if not isinstance(message, dict):
        return repr(message)

    parts: list[str] = []
    content = message.get("content")
    if content is not None:
        text = str(content).replace("\n", "\\n")
        if len(text) > 240:
            text = text[:240] + "…"
        parts.append(f"content={text!r}")

    tool_calls = message.get("tool_calls")
    if tool_calls is not None:
        parts.append(f"tool_calls={json.dumps(tool_calls, ensure_ascii=False)[:400]}")

    if not parts:
        parts.append(f"message keys={list(message.keys())}")

    mode_hint = raw.get("choices", [{}])[0].get("finish_reason")
    if mode_hint:
        parts.append(f"finish_reason={mode_hint!r}")

    return " | ".join(parts)
