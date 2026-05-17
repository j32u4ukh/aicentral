"""Provider 註冊表（v2.0）。"""

from __future__ import annotations

from types import ModuleType

from aicentral.core.errors import ProviderError
from aicentral.providers import openai

_REGISTRY: dict[str, ModuleType] = {
    "ollama": openai,
}


def get_provider_module(name: str) -> ModuleType:
    """依 provider 名稱取得模組（須具 chat_completions 等函式）。"""
    key = name.lower().strip()
    try:
        return _REGISTRY[key]
    except KeyError as exc:
        known = ", ".join(sorted(_REGISTRY))
        raise ProviderError(f"未知 provider: {name!r}（可用: {known}）") from exc
