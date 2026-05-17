"""aicentral — AI capability library for other projects (LLM routing + structured outputs)."""

from aicentral.client import complete
from aicentral.exceptions import AICentralError, ProviderError

__version__ = "0.1.0"
__all__ = ["complete", "AICentralError", "ProviderError", "__version__"]
