"""Gemini 池配額與輪換索引的本地 JSON 持久化（gemini-limit.md 方案二）。"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aicentral.config.loader import repo_root

logger = logging.getLogger(__name__)

STORE_VERSION = 1


def resolve_store_path(path: str | None) -> Path | None:
    if not path or not str(path).strip():
        return None
    p = Path(path.strip())
    if not p.is_absolute():
        p = repo_root() / p
    return p


def default_store_path() -> Path:
    return repo_root() / "config" / "rate_limit_store.json"


def _empty_model_usage() -> dict[str, int]:
    return {
        "minute_epoch": 0,
        "minute_count": 0,
        "day_epoch": 0,
        "day_count": 0,
    }


def new_pool_record(model_ids: list[str], *, model_index: int = 0) -> dict[str, Any]:
    models = {mid: _empty_model_usage() for mid in model_ids}
    next_id = model_ids[model_index % len(model_ids)] if model_ids else None
    return {
        "model_index": model_index % max(len(model_ids), 1),
        "next_model_id": next_id,
        "total_calls": 0,
        "last_success_time": None,
        "models": models,
    }


def load_store_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"version": STORE_VERSION, "pools": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("無法讀取 %s，將重建：%s", path, exc)
        return {"version": STORE_VERSION, "pools": {}}
    if not isinstance(raw, dict):
        return {"version": STORE_VERSION, "pools": {}}
    raw.setdefault("version", STORE_VERSION)
    raw.setdefault("pools", {})
    if not isinstance(raw["pools"], dict):
        raw["pools"] = {}
    return raw


def get_pool_record(
    store: dict[str, Any],
    pool_name: str,
    model_ids: list[str],
) -> dict[str, Any]:
    pools = store.setdefault("pools", {})
    record = pools.get(pool_name)
    if not isinstance(record, dict):
        record = new_pool_record(model_ids)
        pools[pool_name] = record
        return record

    record.setdefault("model_index", 0)
    record.setdefault("total_calls", 0)
    models_map = record.get("models")
    if not isinstance(models_map, dict):
        models_map = {}
        record["models"] = models_map

    for mid in model_ids:
        if mid not in models_map or not isinstance(models_map[mid], dict):
            models_map[mid] = _empty_model_usage()
        else:
            usage = models_map[mid]
            usage.setdefault("minute_epoch", 0)
            usage.setdefault("minute_count", 0)
            usage.setdefault("day_epoch", 0)
            usage.setdefault("day_count", 0)

    # 移除已不在 yaml 的舊 model_id
    for stale in list(models_map.keys()):
        if stale not in model_ids:
            del models_map[stale]

    idx = int(record.get("model_index", 0))
    record["model_index"] = idx % max(len(model_ids), 1)
    record["next_model_id"] = (
        model_ids[record["model_index"]] if model_ids else None
    )
    return record


def save_store_file(path: Path, store: dict[str, Any]) -> None:
    store["version"] = STORE_VERSION
    store["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(store, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


class GeminiRateLimitStore:
    """單一命名池的持久化讀寫（由 ``GeminiPoolLimiter`` 持有）。"""

    def __init__(
        self,
        pool_name: str,
        model_ids: list[str],
        path: Path,
    ) -> None:
        self.pool_name = pool_name
        self.model_ids = list(model_ids)
        self.path = path
        self._document = load_store_file(path)
        self.record = get_pool_record(self._document, pool_name, model_ids)

    def persist(self) -> None:
        idx = int(self.record.get("model_index", 0))
        if self.model_ids:
            self.record["next_model_id"] = self.model_ids[idx % len(self.model_ids)]
        save_store_file(self.path, self._document)

    def sync_from_limiter(
        self,
        usage_rows: dict[str, dict[str, int]],
        *,
        model_index: int,
        total_calls: int,
        last_success_time: float | None,
    ) -> None:
        self.record["models"] = usage_rows
        self.record["model_index"] = model_index
        self.record["total_calls"] = total_calls
        self.record["last_success_time"] = last_success_time
        if self.model_ids:
            self.record["next_model_id"] = self.model_ids[
                model_index % len(self.model_ids)
            ]
