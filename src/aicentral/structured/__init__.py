"""結構化輸出：schema、extract、validate（v3.0）。"""

from aicentral.structured.extract import ExtractMode, from_chat_completion, from_message_content
from aicentral.structured.prompt import with_structured_hint
from aicentral.structured.retry import append_retry_hint
from aicentral.structured.schema import ToolSpec, build_tool
from aicentral.structured.validate import format_validation_errors, parse

__all__ = [
    "ExtractMode",
    "ToolSpec",
    "append_retry_hint",
    "build_tool",
    "format_validation_errors",
    "from_chat_completion",
    "from_message_content",
    "parse",
    "with_structured_hint",
]
