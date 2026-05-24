"""Gemini rate_limit_store.json 持久化測試。"""

import json
from pathlib import Path

from aicentral.config.schema import GeminiPoolModelEntry, GeminiPoolSettings
from aicentral.routing.gemini_pool import GeminiPoolLimiter, reset_gemini_pools
from aicentral.routing.gemini_rate_limit_store import (
    get_pool_record,
    load_store_file,
    new_pool_record,
)


def test_new_pool_record_has_next_model_id() -> None:
    rec = new_pool_record(["a", "b", "c"], model_index=1)
    assert rec["model_index"] == 1
    assert rec["next_model_id"] == "b"


def test_persist_roundtrip(tmp_path: Path) -> None:
    reset_gemini_pools()
    store_path = tmp_path / "rate_limit_store.json"
    settings = GeminiPoolSettings(
        rate_limit_store_path=str(store_path),
        models=[
            GeminiPoolModelEntry(model_id="model-a", rpm_limit=5),
            GeminiPoolModelEntry(model_id="model-b", rpm_limit=5),
        ],
    )
    pool1 = GeminiPoolLimiter.from_settings("t", settings)
    assert pool1.acquire() == "model-a"
    assert pool1._model_index == 1
    assert pool1._total_calls == 1

    reset_gemini_pools()
    pool2 = GeminiPoolLimiter.from_settings("t", settings)
    assert pool2._model_index == 1
    assert pool2._total_calls == 1
    assert pool2.acquire() == "model-b"
    assert pool2._model_index == 0

    data = json.loads(store_path.read_text(encoding="utf-8"))
    rec = data["pools"]["t"]
    assert rec["total_calls"] == 2
    assert rec["next_model_id"] == "model-a"


def test_load_merges_new_models_from_yaml(tmp_path: Path) -> None:
    path = tmp_path / "store.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "pools": {
                    "default": {
                        "model_index": 0,
                        "total_calls": 3,
                        "models": {
                            "old-model": {
                                "minute_epoch": 1,
                                "minute_count": 9,
                                "day_epoch": 1,
                                "day_count": 9,
                            }
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    store = load_store_file(path)
    rec = get_pool_record(store, "default", ["gemini-2.5-flash"])
    assert "old-model" not in rec["models"]
    assert rec["models"]["gemini-2.5-flash"]["minute_count"] == 0
    assert rec["total_calls"] == 3
