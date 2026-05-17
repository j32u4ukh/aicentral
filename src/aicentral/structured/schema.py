"""Pydantic model → OpenAI tools schema。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel


@dataclass(frozen=True)
class ToolSpec:
    """單一 function tool 與對應 tool_choice。"""

    tools: list[dict[str, Any]]
    tool_choice: dict[str, Any]
    tool_name: str


def _tool_name_for_model(model: type[BaseModel]) -> str:
    return model.__name__.lower()


def build_tool(response_model: type[BaseModel]) -> ToolSpec:
    """
    由 Pydantic v2 model 產生 OpenAI ``tools`` 與 ``tool_choice``。

    function ``name`` 為類名小寫（``Ticket`` → ``ticket``）。
    """
    tool_name = _tool_name_for_model(response_model)
    parameters = response_model.model_json_schema()
    description = (response_model.__doc__ or "").strip() or response_model.__name__

    function_def: dict[str, Any] = {
        "name": tool_name,
        "description": description,
        "parameters": parameters,
    }
    tools = [{"type": "function", "function": function_def}]
    tool_choice: dict[str, Any] = {
        "type": "function",
        "function": {"name": tool_name},
    }
    return ToolSpec(tools=tools, tool_choice=tool_choice, tool_name=tool_name)
