"""向後相容：v1.x 的 openai_compat 匯入路徑。"""

from aicentral.providers.openai import (
    DEFAULT_TIMEOUT,
    chat_completions,
    chat_completions_stream,
    to_openai_messages,
)

__all__ = [
    "DEFAULT_TIMEOUT",
    "chat_completions",
    "chat_completions_stream",
    "to_openai_messages",
]
