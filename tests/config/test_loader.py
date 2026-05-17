import os
from pathlib import Path

from aicentral.config.loader import expand_env_value, load_config


def test_expand_env_value() -> None:
    os.environ["TEST_AICENTRAL_KEY"] = "secret"
    assert expand_env_value("os.environ/TEST_AICENTRAL_KEY") == "secret"
    assert expand_env_value({"k": "os.environ/TEST_AICENTRAL_KEY"}) == {"k": "secret"}


def test_load_config_from_repo_example() -> None:
    path = Path(__file__).resolve().parents[2] / "config" / "aicentral.yaml"
    cfg = load_config(path=path, reload=True)
    assert cfg.model_entry_by_name("local-chat") is not None
    assert cfg.model_entry_by_name("local-chat").provider == "ollama"
    assert "deepwiki" in cfg.mcp_servers


def test_load_config_missing_returns_empty(tmp_path: Path) -> None:
    cfg = load_config(path=tmp_path / "missing.yaml", reload=True)
    assert cfg.model_list == []
