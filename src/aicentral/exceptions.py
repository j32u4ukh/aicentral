"""向後相容：請改用 ``aicentral.core.errors``。"""

from aicentral.core.errors import (
    AICentralError,
    HistoryOverflowError,
    ProviderError,
    StructuredOutputError,
)

__all__ = [
    "AICentralError",
    "HistoryOverflowError",
    "ProviderError",
    "StructuredOutputError",
]
