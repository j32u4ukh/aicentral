"""aicentral — AI capability library for other projects (LLM routing + structured outputs)."""

from aicentral.chat import Chat, ChatMode, HistoryPolicy
from aicentral.core.client import complete
from aicentral.core.errors import AICentralError, HistoryOverflowError, ProviderError
from aicentral.core.types import ChatResponse, Message, Role
from aicentral.routing.parser import ParsedModel, parse_model

__version__ = "0.3.0"
__all__ = [
    "Chat",
    "ChatMode",
    "ChatResponse",
    "HistoryPolicy",
    "Message",
    "ParsedModel",
    "Role",
    "complete",
    "parse_model",
    "AICentralError",
    "HistoryOverflowError",
    "ProviderError",
    "__version__",
]
