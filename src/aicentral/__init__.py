"""aicentral — AI capability library for other projects (LLM routing + structured outputs)."""

from aicentral.chat import Chat, ChatMode, HistoryPolicy
from aicentral.core.client import complete, complete_structured
from aicentral.core.errors import (
    AICentralError,
    HistoryOverflowError,
    ProviderError,
    StructuredFailureKind,
    StructuredNoPayloadError,
    StructuredOutputError,
    StructuredValidationError,
)
from aicentral.core.types import ChatResponse, Message, Role
from aicentral.routing.parser import ParsedModel, parse_model
from aicentral.structured.retry import append_retry_hint

__version__ = "0.4.0"
__all__ = [
    "Chat",
    "ChatMode",
    "ChatResponse",
    "HistoryPolicy",
    "Message",
    "ParsedModel",
    "Role",
    "complete",
    "complete_structured",
    "parse_model",
    "append_retry_hint",
    "AICentralError",
    "HistoryOverflowError",
    "ProviderError",
    "StructuredFailureKind",
    "StructuredNoPayloadError",
    "StructuredOutputError",
    "StructuredValidationError",
    "__version__",
]
