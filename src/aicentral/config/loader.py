"""載入 aicentral.yaml 與 env 覆寫。"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from aicentral.config.schema import AICentralConfig

_ENV_PREFIX = "os.environ/"


def expand_env_value(value: Any) -> Any:
    """展開 ``os.environ/VAR`` 字串；遞迴處理 dict / list。"""
    if isinstance(value, str):
        if value.startswith(_ENV_PREFIX):
            key = value[len(_ENV_PREFIX) :]
            return os.getenv(key, "")
        return value
    if isinstance(value, dict):
        return {k: expand_env_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [expand_env_value(v) for v in value]
    return value


def _config_search_paths() -> list[Path]:
    paths: list[Path] = []
    explicit = os.getenv("AICENTRAL_CONFIG")
    if explicit:
        paths.append(Path(explicit))
    paths.extend(
        [
            Path("aicentral.yaml"),
            Path("config/aicentral.yaml"),
        ]
    )
    return paths


def load_config(*, path: str | Path | None = None, reload: bool = False) -> AICentralConfig:
    """載入設定；找不到 yaml 時回傳空設定（沿用 env）。"""
    load_dotenv()
    if reload:
        get_config.cache_clear()

    if path is not None:
        p = Path(path)
        if not p.is_file():
            return AICentralConfig()
        return _load_yaml_path(p)

    for candidate in _config_search_paths():
        if candidate.is_file():
            return _load_yaml_path(candidate)

    return AICentralConfig()


def _load_yaml_path(path: Path) -> AICentralConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return AICentralConfig()
    if not isinstance(raw, dict):
        raise ValueError(f"設定檔格式錯誤（須為 mapping）: {path}")
    expanded = expand_env_value(raw)
    return AICentralConfig.model_validate(expanded)


@lru_cache(maxsize=1)
def get_config() -> AICentralConfig:
    return load_config()
