"""依 provider 解析 base_url / api_key（來自已展開的 params 或 secret.yaml）。"""

from __future__ import annotations

from aicentral.config.loader import get_secret
from aicentral.config.schema import ModelParams, ProviderName

_DEFAULT_OLLAMA_BASE = "http://localhost:11434/v1"
_DEFAULT_ANTHROPIC_VERSION = "2023-06-01"
_DEFAULT_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


def resolve_credentials(
    provider: ProviderName,
    params: ModelParams,
) -> tuple[str | None, str | None, str | None]:
    """回傳 (api_base, api_key, api_version)。"""
    if provider == "ollama":
        base = params.api_base or get_secret("ollama.base_url", default=_DEFAULT_OLLAMA_BASE)
        key = params.api_key
        if key is None or key == "":
            key = get_secret("ollama.api_key", default="ollama")
        return base, key or None, params.api_version
    if provider == "openai":
        base = params.api_base or get_secret("openai.api_base", default="https://api.openai.com/v1")
        key = params.api_key or get_secret("openai.api_key")
        return base, key, params.api_version
    if provider == "anthropic":
        base = params.api_base or get_secret("anthropic.api_base", default="https://api.anthropic.com")
        key = params.api_key or get_secret("anthropic.api_key")
        version = params.api_version or get_secret(
            "anthropic.api_version", default=_DEFAULT_ANTHROPIC_VERSION
        )
        return base, key, version
    if provider == "gemini":
        base = params.api_base or get_secret("gemini.api_base", default=_DEFAULT_GEMINI_BASE)
        key = params.api_key or get_secret("gemini.api_key")
        return base, key, params.api_version
    return params.api_base, params.api_key, params.api_version
