"""aicentral — AI capability library for other projects (LLM routing + structured outputs)."""

from aicentral.chat import Chat, ChatMode, HistoryPolicy
from aicentral.history import History
from aicentral.config import get_config, load_config
from aicentral.core.client import complete, complete_structured, embedding
from aicentral.core.errors import (
    AICentralError,
    HistoryOverflowError,
    ProviderError,
    StructuredFailureKind,
    StructuredNoPayloadError,
    StructuredOutputError,
    StructuredValidationError,
)
from aicentral.core.types import ChatResponse, Message, Role, as_messages, user_message
from aicentral.mcp import (
    MCPManager,
    MCPServerEntry,
    ask_mcp,
    register_mcp_server,
    register_mcp_servers,
    registered_mcp_servers,
    unregister_mcp_server,
)
from aicentral.routing.parser import ParsedModel, parse_model
from aicentral.routing.router import ResolvedCall, effective_model, resolve_call
from aicentral.structured.retry import append_retry_hint

__version__ = "0.6.1"
__all__ = [
    "Chat",
    "ChatMode",
    "ChatResponse",
    "History",
    "HistoryPolicy",
    "embedding",
    "Message",
    "ParsedModel",
    "Role",
    "as_messages",
    "user_message",
    "ask_mcp",
    "complete",
    "complete_structured",
    "parse_model",
    "get_config",
    "load_config",
    "ResolvedCall",
    "resolve_call",
    "effective_model",
    "MCPManager",
    "MCPServerEntry",
    "register_mcp_server",
    "register_mcp_servers",
    "registered_mcp_servers",
    "unregister_mcp_server",
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
