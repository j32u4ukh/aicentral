from pathlib import Path

import pytest
import yaml

from aicentral.config.loader import (
    expand_config_value,
    get_nested,
    load_config,
    load_secrets,
    repo_root,
)
from aicentral.config.schema import AICentralConfig


def test_get_nested() -> None:
    data = {"ollama": {"api_key": "k"}, "mcp": {"linear": {"api_key": "l"}}}
    assert get_nested(data, "ollama.api_key") == "k"
    assert get_nested(data, "mcp.linear.api_key") == "l"


def test_expand_secret_reference() -> None:
    secrets = {"openai": {"api_key": "sk-test"}}
    assert expand_config_value("secret/openai.api_key", secrets) == "sk-test"
    assert expand_config_value(
        {"params": {"api_key": "secret/openai.api_key"}},
        secrets,
    ) == {"params": {"api_key": "sk-test"}}


def test_load_config_from_repo_files() -> None:
    root = repo_root()
    cfg = load_config(
        path=root / "config" / "aicentral.yaml",
        secrets_path=root / "config" / "secret.yaml",
        reload=True,
    )
    entry = cfg.model_entry_by_name("local-chat")
    assert entry is not None
    assert entry.provider == "ollama"
    assert entry.params.api_base == "http://localhost:11434/v1"
    assert cfg.defaults.model == "local-chat"
    assert "請一律使用繁體中文" in (cfg.aicentral_settings.system_prompt or "")


def test_load_config_missing_main_returns_empty(tmp_path: Path) -> None:
    secrets = tmp_path / "secret.yaml"
    secrets.write_text(yaml.dump({"ollama": {"model": "x"}}), encoding="utf-8")
    cfg = load_config(path=tmp_path / "missing.yaml", secrets_path=secrets, reload=True)
    assert cfg.model_list == []


def test_load_config_expands_mcp_secret(tmp_path: Path) -> None:
    secret = tmp_path / "secret.yaml"
    secret.write_text(
        yaml.dump({"mcp": {"demo": {"auth_value": "token-123"}}}),
        encoding="utf-8",
    )
    main = tmp_path / "aicentral.yaml"
    main.write_text(
        yaml.dump(
            {
                "mcp_servers": {
                    "demo_srv": {
                        "transport": "http",
                        "url": "https://example.com/mcp",
                        "auth_type": "bearer_token",
                        "auth_value": "secret/mcp.demo.auth_value",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    cfg = load_config(path=main, secrets_path=secret, reload=True)
    assert cfg.mcp_servers["demo_srv"].auth_value == "token-123"
