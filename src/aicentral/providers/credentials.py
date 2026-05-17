"""依 provider 解析預設 base_url / api_key（config 未填時）。"""

from __future__ import annotations

import os

from aicentral.config.schema import ModelParams, ProviderName


def resolve_credentials(
    provider: ProviderName,
    params: ModelParams,
) -> tuple[str | None, str | None, str | None]:
    """回傳 (api_base, api_key, api_version)。"""
    if provider == "ollama":
        base = params.api_base or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        key = params.api_key
        if key is None:
            key = os.getenv("OLLAMA_API_KEY", "ollama")
        return base, key or None, params.api_version
    if provider == "openai":
        base = params.api_base or os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
        key = params.api_key or os.getenv("OPENAI_API_KEY")
        return base, key, params.api_version
    if provider == "anthropic":
        base = params.api_base or os.getenv("ANTHROPIC_API_BASE", "https://api.anthropic.com")
        key = params.api_key or os.getenv("ANTHROPIC_API_KEY")
        version = params.api_version or os.getenv("ANTHROPIC_API_VERSION", "2023-06-01")
        return base, key, version
    if provider == "gemini":
        base = params.api_base or os.getenv(
            "GEMINI_API_BASE",
            "https://generativelanguage.googleapis.com/v1beta",
        )
        key = params.api_key or os.getenv("GEMINI_API_KEY")
        return base, key, params.api_version
    return params.api_base, params.api_key, params.api_version
