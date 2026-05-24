"""Gemini rate_limit_store.json 持久化測試。"""

import json
import time
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


def test_load_syncs_stale_epoch_and_persists(tmp_path: Path) -> None:
    reset_gemini_pools()
    store_path = tmp_path / "store.json"
    stale_minute = int(time.time() // 60) - 2
    store_path.write_text(
        json.dumps(
            {
                "version": 1,
                "pools": {
                    "t": {
                        "model_index": 0,
                        "total_calls": 1,
                        "models": {
                            "m": {
                                "minute_epoch": stale_minute,
                                "minute_count": 7,
                                "day_epoch": 0,
                                "day_count": 0,
                            }
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    settings = GeminiPoolSettings(
        rate_limit_store_path=str(store_path),
        models=[GeminiPoolModelEntry(model_id="m", rpm_limit=5)],
    )
    pool = GeminiPoolLimiter.from_settings("t", settings)
    counters = pool._counters_for("m")
    assert counters.minute_count == 0
    assert counters.minute_epoch == int(time.time() // 60)

    data = json.loads(store_path.read_text(encoding="utf-8"))
    row = data["pools"]["t"]["models"]["m"]
    assert row["minute_count"] == 0
    assert row["minute_epoch"] == counters.minute_epoch


def test_success_without_headers_persists_last_success(tmp_path: Path) -> None:
    reset_gemini_pools()
    store_path = tmp_path / "store.json"
    settings = GeminiPoolSettings(
        rate_limit_store_path=str(store_path),
        models=[GeminiPoolModelEntry(model_id="m", rpm_limit=5)],
    )
    pool = GeminiPoolLimiter.from_settings("t", settings)
    pool.apply_headers("m", {}, status_code=200)
    assert pool._last_success_time is not None

    data = json.loads(store_path.read_text(encoding="utf-8"))
    assert data["pools"]["t"]["last_success_time"] == pool._last_success_time
