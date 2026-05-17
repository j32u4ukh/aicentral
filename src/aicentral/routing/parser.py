"""model 字串解析：provider/model_id。"""

from __future__ import annotations

from typing import NamedTuple

from aicentral.config.loader import get_secret

DEFAULT_PROVIDER = "ollama"
KNOWN_PROVIDERS = frozenset({"ollama", "openai", "anthropic", "gemini"})


class ParsedModel(NamedTuple):
    provider: str
    model_id: str


def parse_model(model: str | None) -> ParsedModel:
    """
    解析 model 參數。

    - ``None`` / 空字串 → ``(ollama, secret.yaml ollama.model)``
    - ``gemma4:e2b`` → ``(ollama, gemma4:e2b)``（裸名，向後相容）
    - ``ollama/gemma4:e2b`` → ``(ollama, gemma4:e2b)``
    """
    if model is None or not str(model).strip():
        model_id = get_secret("ollama.model", default="gemma4:e2b") or "gemma4:e2b"
        return ParsedModel(DEFAULT_PROVIDER, model_id)

    text = model.strip()
    if "/" in text:
        provider, _, model_id = text.partition("/")
        provider = provider.strip().lower()
        model_id = model_id.strip()
        if not provider or not model_id:
            raise ValueError(f"無效的 model 字串: {model!r}")
        if provider not in KNOWN_PROVIDERS:
            raise ValueError(
                f"未知 provider: {provider!r}（可用: {', '.join(sorted(KNOWN_PROVIDERS))}）"
            )
        return ParsedModel(provider, model_id)

    return ParsedModel(DEFAULT_PROVIDER, text)
