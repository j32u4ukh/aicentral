from unittest.mock import MagicMock, patch

import pytest

from aicentral.config.schema import (
    AICentralConfig,
    FallbackEntry,
    ModelEntry,
    ModelParams,
    RouterSettings,
)
from aicentral.core.errors import ProviderError
from aicentral.routing.router import (
    complete_with_fallback,
    effective_model,
    resolve_call,
    resolve_fallback_chain,
)


def _sample_config() -> AICentralConfig:
    return AICentralConfig(
        model_list=[
            ModelEntry(
                model_name="local-chat",
                provider="ollama",
                params=ModelParams(
                    model_id="gemma4:e2b",
                    api_base="http://localhost:11434/v1",
                    api_key="ollama",
                ),
            ),
            ModelEntry(
                model_name="cloud-chat",
                provider="openai",
                params=ModelParams(
                    model_id="gpt-4o-mini",
                    api_base="https://api.openai.com/v1",
                    api_key="sk-test",
                ),
            ),
        ],
        router=RouterSettings(
            fallbacks=[FallbackEntry(model_name="local-chat", fallbacks=["cloud-chat"])],
            fallback_on=["connection_error", "timeout"],
        ),
    )


def test_effective_model_none_uses_env_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AICENTRAL_DEFAULT_MODEL", "openai/gpt-4o-mini")
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    assert effective_model(None) == "openai/gpt-4o-mini"


def test_effective_model_none_falls_back_to_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AICENTRAL_DEFAULT_MODEL", raising=False)
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.2")
    assert effective_model(None, config=AICentralConfig()) == "ollama/llama3.2"


def test_effective_model_explicit_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AICENTRAL_DEFAULT_MODEL", "openai/gpt-4o-mini")
    assert effective_model("anthropic/claude-3") == "anthropic/claude-3"


def test_resolve_call_alias() -> None:
    cfg = _sample_config()
    resolved = resolve_call("cloud-chat", config=cfg)
    assert resolved.provider == "openai"
    assert resolved.model_id == "gpt-4o-mini"
    assert resolved.api_key == "sk-test"


def test_resolve_fallback_chain() -> None:
    cfg = _sample_config()
    chain = resolve_fallback_chain("local-chat", config=cfg)
    assert [c.model_label for c in chain] == ["local-chat", "cloud-chat"]


@patch("aicentral.providers.openai.chat_completions")
def test_complete_with_fallback_on_connection_error(mock_chat: MagicMock) -> None:
    cfg = _sample_config()
    mock_chat.side_effect = [
        ProviderError("無法連線", failure_kind="connection_error"),
        "ok from cloud",
    ]
    result = complete_with_fallback(
        [{"role": "user", "content": "hi"}],
        "local-chat",
        config=cfg,
    )
    assert result == "ok from cloud"
    assert mock_chat.call_count == 2


@patch("aicentral.providers.openai.chat_completions")
def test_complete_no_fallback_on_http_401(mock_chat: MagicMock) -> None:
    cfg = _sample_config()
    mock_chat.side_effect = ProviderError("unauthorized", status_code=401, failure_kind="http")
    with pytest.raises(ProviderError):
        complete_with_fallback(
            [{"role": "user", "content": "hi"}],
            "local-chat",
            config=cfg,
        )
    assert mock_chat.call_count == 1
