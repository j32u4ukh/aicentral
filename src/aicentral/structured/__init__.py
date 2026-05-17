"""結構化輸出：schema、extract、validate（v3.0）。"""

from aicentral.structured.extract import from_chat_completion
from aicentral.structured.schema import ToolSpec, build_tool
from aicentral.structured.validate import format_validation_errors, parse

__all__ = [
    "ToolSpec",
    "build_tool",
    "format_validation_errors",
    "from_chat_completion",
    "parse",
]
