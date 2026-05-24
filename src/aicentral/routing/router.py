"""v4.0：model 別名解析與 fallback 鏈。"""

from __future__ import annotations

import logging
import time
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
from aicentral.routing.gemini_pool import get_gemini_pool, reset_gemini_pools
from aicentral.routing.parser import parse_model

logger = logging.getLogger(__name__)

KNOWN_PROVIDERS = frozenset({"ollama", "openai", "anthropic", "gemini"})

_GEMINI_POOL_KEY = "_gemini_pool"
_GEMINI_MODEL_ID_KEY = "_gemini_model_id"


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


def effective_embedding_model(
    model: str | None,
    *,
    config: AICentralConfig | None = None,
) -> str:
    """
    歷史向量分群用的 embedding 模型（與對話 ``model`` 分開設定）。

    1. 參數 ``model``（非空）
    2. ``defaults.embedding_model``
    3. ``local-embed``（需在 ``model_list`` 定義；見 config/aicentral.yaml）
    """
    if model is not None and str(model).strip():
        return model.strip()

    cfg = config or get_config()
    emb = (cfg.defaults.embedding_model or "").strip()
    if emb:
        return emb

    return "local-embed"


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
    gemini_pool: str | None = None


def _resolved_from_entry(entry: ModelEntry, cfg: AICentralConfig) -> ResolvedCall:
    base, key, version = resolve_credentials(entry.provider, entry.params)
    pool_name = (entry.gemini_pool or "").strip() or None
    if pool_name and entry.provider != "gemini":
        raise ProviderError(
            f"model_list.{entry.model_name!r} 設了 gemini_pool 但 provider 不是 gemini"
        )
    if pool_name and not cfg.gemini_pool_settings(pool_name):
        raise ProviderError(
            f"未定義 gemini_pools.{pool_name!r}（model {entry.model_name!r}）"
        )
    return ResolvedCall(
        provider=entry.provider,
        model_id=entry.params.model_id,
        model_label=entry.model_name,
        base_url=base,
        api_key=key,
        api_version=version,
        timeout=entry.timeout or cfg.defaults.timeout,
        gemini_pool=pool_name,
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


def _is_rate_limit_error(exc: ProviderError) -> bool:
    if exc.status_code == 429:
        return True
    if exc.failure_kind == "rate_limit":
        return True
    msg = str(exc).lower()
    return "rate limit" in msg or "quota" in msg or "resource exhausted" in msg


def _invoke_provider_once(
    resolved: ResolvedCall,
    messages: list[Message],
    *,
    stream: bool = False,
    raw: bool = False,
    model_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> str | Iterator[str] | dict[str, Any]:
    """對單一 model_id 呼叫 provider（不含池輪換）。"""
    call_extra = dict(extra or {})
    effective = resolved
    if model_id is not None and model_id != resolved.model_id:
        effective = ResolvedCall(
            provider=resolved.provider,
            model_id=model_id,
            model_label=resolved.model_label,
            base_url=resolved.base_url,
            api_key=resolved.api_key,
            api_version=resolved.api_version,
            timeout=resolved.timeout,
            gemini_pool=None,
        )
    provider = get_provider_module(effective.provider)
    call_kw = _provider_kwargs(effective, messages, call_extra)
    if raw:
        return provider.chat_completions_raw(**call_kw)
    if stream:
        return provider.chat_completions_stream(**call_kw)
    return provider.chat_completions(**call_kw)


def _invoke_with_gemini_pool(
    resolved: ResolvedCall,
    messages: list[Message],
    *,
    cfg: AICentralConfig,
    stream: bool = False,
    raw: bool = False,
    extra: dict[str, Any] | None = None,
) -> str | Iterator[str] | dict[str, Any]:
    assert resolved.gemini_pool is not None
    settings = cfg.gemini_pool_settings(resolved.gemini_pool)
    assert settings is not None
    pool = get_gemini_pool(resolved.gemini_pool, settings)
    call_extra = dict(extra or {})
    last_exc: ProviderError | None = None
    attempts = 0
    max_attempts = max(len(pool.models) * 3, 1)
    while attempts < max_attempts:
        attempts += 1
        model_id = pool.acquire()
        call_extra[_GEMINI_POOL_KEY] = pool
        call_extra[_GEMINI_MODEL_ID_KEY] = model_id
        try:
            result = _invoke_provider_once(
                resolved,
                messages,
                stream=stream,
                raw=raw,
                model_id=model_id,
                extra=call_extra,
            )
            pool.reset_429_backoff()
            return result
        except ProviderError as exc:
            last_exc = exc
            if _is_rate_limit_error(exc):
                # 方案四：退讓後換模型；計數已在 gemini.apply_headers(429) 上調，此處再保險一次
                pool.mark_minute_exhausted(model_id)
                wait_s = pool.backoff_seconds_for_429(exc.retry_after_seconds)
                logger.warning(
                    "Gemini 429（%s），%.1fs 後切換下一模型（池 %s）",
                    model_id,
                    wait_s,
                    resolved.gemini_pool,
                )
                time.sleep(wait_s)
                continue
            raise
    assert last_exc is not None
    raise last_exc


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
        try:
            if resolved.gemini_pool:
                if stream:
                    raise ProviderError(
                        "Gemini 模型池尚不支援串流",
                        failure_kind="unsupported",
                    )
                return _invoke_with_gemini_pool(
                    resolved,
                    messages,
                    cfg=cfg,
                    stream=False,
                    raw=False,
                    extra=dict(kwargs),
                )
            return _invoke_provider_once(
                resolved,
                messages,
                stream=stream,
                raw=False,
                extra=dict(kwargs),
            )
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
    config: AICentralConfig | None = None,
    **kwargs: Any,
) -> str | Iterator[str] | dict[str, Any]:
    """對已解析的單一 provider 發起呼叫（供 complete_structured / MCP）。"""
    cfg = config or get_config()
    if resolved.gemini_pool:
        if stream:
            raise ProviderError("Gemini 模型池尚不支援串流", failure_kind="unsupported")
        return _invoke_with_gemini_pool(
            resolved,
            messages,
            cfg=cfg,
            stream=False,
            raw=raw,
            extra=dict(kwargs),
        )
    return _invoke_provider_once(
        resolved,
        messages,
        stream=stream,
        raw=raw,
        extra=dict(kwargs),
    )


__all__ = [
    "ResolvedCall",
    "complete_with_fallback",
    "effective_embedding_model",
    "effective_model",
    "invoke_resolved",
    "reset_gemini_pools",
    "resolve_call",
    "resolve_fallback_chain",
]
