"""v4.0：model 別名解析與 fallback 鏈。"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from aicentral.config import get_config
from aicentral.config.loader import get_secret
from aicentral.config.schema import AICentralConfig, ModelEntry, ModelParams
from aicentral.core.errors import ProviderError
from aicentral.core.types import Message
from aicentral.providers.credentials import resolve_credentials
from aicentral.providers.registry import get_provider_module
from aicentral.routing.parser import parse_model

KNOWN_PROVIDERS = frozenset({"ollama", "openai", "anthropic", "gemini"})


def effective_model(
    model: str | None,
    *,
    config: AICentralConfig | None = None,
) -> str:
    """
    呼叫端未指定 ``model`` 時的實際模型字串（優先序）：

    1. 參數 ``model``（非空）
    2. ``config/aicentral.yaml`` 的 ``defaults.model``
    3. ``ollama/{secret.yaml → ollama.model}``
    """
    if model is not None and str(model).strip():
        return model.strip()

    cfg = config or get_config()
    default = (cfg.defaults.model or "").strip()
    if default:
        return default

    ollama_model = get_secret("ollama.model", default="gemma4:e2b")
    return f"ollama/{ollama_model}"


@dataclass(frozen=True)
class ResolvedCall:
    """一次 LLM 呼叫的解析結果。"""

    provider: str
    model_id: str
    model_label: str
    base_url: str | None
    api_key: str | None
    api_version: str | None
    timeout: float


def _resolved_from_entry(entry: ModelEntry, cfg: AICentralConfig) -> ResolvedCall:
    base, key, version = resolve_credentials(entry.provider, entry.params)
    return ResolvedCall(
        provider=entry.provider,
        model_id=entry.params.model_id,
        model_label=entry.model_name,
        base_url=base,
        api_key=key,
        api_version=version,
        timeout=entry.timeout or cfg.defaults.timeout,
    )


def resolve_call(
    model: str | None,
    *,
    config: AICentralConfig | None = None,
) -> ResolvedCall:
    """解析單次呼叫（不含 fallback 鏈）。"""
    cfg = config or get_config()
    effective = effective_model(model, config=cfg)

    if entry := cfg.model_entry_by_name(effective):
        return _resolved_from_entry(entry, cfg)

    parsed = parse_model(effective)
    if parsed.provider not in KNOWN_PROVIDERS:
        raise ProviderError(
            f"未知 provider: {parsed.provider!r}（可用: {', '.join(sorted(KNOWN_PROVIDERS))}）"
        )

    params = ModelParams(model_id=parsed.model_id)
    base, key, version = resolve_credentials(parsed.provider, params)  # type: ignore[arg-type]
    return ResolvedCall(
        provider=parsed.provider,
        model_id=parsed.model_id,
        model_label=effective,
        base_url=base,
        api_key=key,
        api_version=version,
        timeout=cfg.defaults.timeout,
    )


def resolve_fallback_chain(
    model: str | None,
    *,
    config: AICentralConfig | None = None,
) -> list[ResolvedCall]:
    cfg = config or get_config()
    default_name = effective_model(model, config=cfg)

    names = cfg.fallback_chain(default_name)
    seen: set[str] = set()
    calls: list[ResolvedCall] = []
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        calls.append(resolve_call(name, config=cfg))
    return calls or [resolve_call(default_name, config=cfg)]


def _provider_kwargs(
    resolved: ResolvedCall,
    messages: list[Message],
    extra: dict[str, Any],
) -> dict[str, Any]:
    kw: dict[str, Any] = {
        "messages": messages,
        "model": resolved.model_id,
        "base_url": resolved.base_url,
        "api_key": resolved.api_key,
        "timeout": extra.pop("timeout", resolved.timeout),
        **extra,
    }
    if resolved.api_version and resolved.provider == "anthropic":
        kw["api_version"] = resolved.api_version
    return kw


def complete_with_fallback(
    messages: list[Message],
    model: str | None,
    *,
    stream: bool = False,
    config: AICentralConfig | None = None,
    **kwargs: Any,
) -> str | Iterator[str]:
    cfg = config or get_config()
    chain = resolve_fallback_chain(model, config=cfg)
    attempted: list[str] = []
    last_exc: ProviderError | None = None

    for i, resolved in enumerate(chain):
        attempted.append(resolved.model_label)
        provider = get_provider_module(resolved.provider)
        call_kw = _provider_kwargs(resolved, messages, dict(kwargs))
        try:
            if stream:
                return provider.chat_completions_stream(**call_kw)
            return provider.chat_completions(**call_kw)
        except ProviderError as exc:
            last_exc = exc
            if exc.is_fallback_eligible(cfg.router.fallback_on) and i < len(chain) - 1:
                continue
            exc.add_note(f"已嘗試 model: {', '.join(attempted)}")
            raise

    assert last_exc is not None
    raise last_exc


def invoke_resolved(
    resolved: ResolvedCall,
    messages: list[Message],
    *,
    stream: bool = False,
    raw: bool = False,
    **kwargs: Any,
) -> str | Iterator[str] | dict[str, Any]:
    """對已解析的單一 provider 發起呼叫（供 complete_structured）。"""
    provider = get_provider_module(resolved.provider)
    call_kw = _provider_kwargs(resolved, messages, dict(kwargs))
    if raw:
        return provider.chat_completions_raw(**call_kw)
    if stream:
        return provider.chat_completions_stream(**call_kw)
    return provider.chat_completions(**call_kw)
