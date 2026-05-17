"""OpenAI 相容 SSE 串流解析（v1.1）。"""

from __future__ import annotations

import json
from typing import Any


def parse_sse_data_line(line: str) -> dict[str, Any] | None:
    """解析 ``data: {...}`` 行；``[DONE]`` 或無效行回傳 None。"""
    stripped = line.strip()
    if not stripped.startswith("data:"):
        return None
    payload = stripped[5:].strip()
    if not payload or payload == "[DONE]":
        return None
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def extract_delta_content(chunk: dict[str, Any]) -> str | None:
    """自 chunk JSON 取出 ``choices[0].delta.content``。"""
    try:
        content = chunk["choices"][0]["delta"]["content"]
    except (KeyError, IndexError, TypeError):
        return None
    if content is None:
        return None
    text = str(content)
    return text if text else None
