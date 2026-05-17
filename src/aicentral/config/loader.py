"""載入 config/aicentral.yaml 與 config/secret.yaml（巢狀 secret 引用）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from aicentral.config.schema import AICentralConfig

_SECRET_PREFIX = "secret/"
_SECRETS: dict[str, Any] | None = None
_CONFIG: AICentralConfig | None = None


def repo_root() -> Path:
    """aicentral 套件 repo 根目錄（含 config/）。"""
    return Path(__file__).resolve().parents[3]


def default_main_config_path() -> Path:
    return repo_root() / "config" / "aicentral.yaml"


def default_secrets_config_path() -> Path:
    return repo_root() / "config" / "secret.yaml"


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"設定檔格式錯誤（須為 mapping）: {path}")
    return raw


def get_nested(data: dict[str, Any], path: str) -> Any:
    """以 ``ollama.api_key`` 形式讀取巢狀 dict。"""
    node: Any = data
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(path)
        node = node[part]
    return node


def resolve_secret(path: str, secrets: dict[str, Any]) -> str:
    value = get_nested(secrets, path)
    if value is None:
        return ""
    return str(value)


def expand_config_value(value: Any, secrets: dict[str, Any]) -> Any:
    """展開 ``secret/ollama.api_key`` 等引用。"""
    if isinstance(value, str):
        if value.startswith(_SECRET_PREFIX):
            ref = value[len(_SECRET_PREFIX) :]
            return resolve_secret(ref, secrets)
        return value
    if isinstance(value, dict):
        return {k: expand_config_value(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [expand_config_value(v, secrets) for v in value]
    return value


def load_secrets(*, path: Path | None = None) -> dict[str, Any]:
    """載入 secret.yaml（巢狀結構）。"""
    global _SECRETS
    p = path or default_secrets_config_path()
    _SECRETS = _load_yaml_mapping(p)
    return _SECRETS


def get_secrets() -> dict[str, Any]:
    """已載入的 secrets；若尚未載入則讀取預設路徑。"""
    if _SECRETS is None:
        return load_secrets()
    return _SECRETS


def get_secret(path: str, *, default: str | None = None) -> str | None:
    """
    讀取 secret 巢狀路徑，例如 ``ollama.api_key``。

    找不到時回傳 ``default``；無 default 且缺少鍵時回傳 ``None``。
    """
    try:
        value = get_nested(get_secrets(), path)
    except KeyError:
        return default
    if value is None or value == "":
        return default
    return str(value)


def load_config(
    *,
    path: str | Path | None = None,
    secrets_path: str | Path | None = None,
    reload: bool = False,
) -> AICentralConfig:
    """載入 main yaml 並以 secret.yaml 展開 ``secret/...`` 引用；同步更新 ``get_config()``。"""
    global _SECRETS, _CONFIG
    if reload:
        _SECRETS = None
        _CONFIG = None

    secrets = load_secrets(path=Path(secrets_path) if secrets_path else None)
    main_path = Path(path) if path else default_main_config_path()
    if not main_path.is_file():
        _CONFIG = AICentralConfig()
        return _CONFIG

    raw = _load_yaml_mapping(main_path)
    expanded = expand_config_value(raw, secrets)
    _CONFIG = AICentralConfig.model_validate(expanded)
    return _CONFIG


def get_config() -> AICentralConfig:
    """目前載入的設定；尚未載入時讀取預設路徑。"""
    if _CONFIG is None:
        return load_config()
    return _CONFIG


def get_default_model() -> str | None:
    """``defaults.model``（已展開 secret）。"""
    model = get_config().defaults.model
    return model.strip() if model else None


def get_structured_mode() -> str:
    mode = get_config().defaults.structured_mode
    if mode and str(mode).strip().lower() == "json":
        return "json"
    return "tool"


def get_system_prompt(default: str) -> str:
    prompt = get_config().aicentral_settings.system_prompt
    if prompt and prompt.strip():
        return prompt.strip()
    return default


def is_dev_mode_from_config() -> bool:
    return get_config().aicentral_settings.dev
