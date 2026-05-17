from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from aicentral.config.loader import load_config, repo_root
from aicentral.config.schema import (
    AICentralConfig,
    DefaultsSettings,
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
        defaults=DefaultsSettings(),
    )


def test_effective_model_uses_defaults() -> None:
    cfg = AICentralConfig(defaults={"model": "local-chat", "timeout": 120.0})
    assert effective_model(None, config=cfg) == "local-chat"


def test_effective_model_falls_back_to_secret_ollama_model(tmp_path: Path) -> None:
    secret = tmp_path / "secret.yaml"
    secret.write_text(yaml.dump({"ollama": {"model": "llama3.2"}}), encoding="utf-8")
    empty = tmp_path / "empty.yaml"
    empty.write_text("", encoding="utf-8")
    load_config(path=empty, secrets_path=secret, reload=True)
    cfg = AICentralConfig()
    assert effective_model(None, config=cfg) == "ollama/llama3.2"


def test_effective_model_explicit_wins() -> None:
    cfg = AICentralConfig(defaults={"model": "local-chat", "timeout": 120.0})
    assert effective_model("anthropic/claude-3", config=cfg) == "anthropic/claude-3"


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


def test_effective_model_from_repo_yaml() -> None:
    load_config(
        path=repo_root() / "config" / "aicentral.yaml",
        secrets_path=repo_root() / "config" / "secret.yaml",
        reload=True,
    )
    assert effective_model(None) == "local-chat"
