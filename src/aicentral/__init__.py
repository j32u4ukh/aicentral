"""aicentral — AI capability library for other projects (LLM routing + structured outputs)."""

from aicentral.chat import Chat, ChatMode, HistoryPolicy
from aicentral.client import complete
from aicentral.exceptions import AICentralError, HistoryOverflowError, ProviderError
from aicentral.types import Message

__version__ = "0.2.0"
__all__ = [
    "Chat",
    "ChatMode",
    "HistoryPolicy",
    "Message",
    "complete",
    "AICentralError",
    "HistoryOverflowError",
    "ProviderError",
    "__version__",
]
