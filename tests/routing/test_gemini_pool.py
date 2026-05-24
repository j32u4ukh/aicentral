"""Gemini 模型池限流與輪換測試。"""

from unittest.mock import MagicMock, patch

import pytest

from aicentral.config.schema import GeminiPoolModelEntry, GeminiPoolSettings
from aicentral.core.errors import ProviderError
from aicentral.routing.gemini_pool import GeminiPoolLimiter, reset_gemini_pools


def _pool_two_models() -> GeminiPoolLimiter:
    return GeminiPoolLimiter.from_settings(
        "test",
        GeminiPoolSettings(
            wait_poll_seconds=0.1,
            models=[
                GeminiPoolModelEntry(
                    model_id="model-a",
                    rpm_official=10,
                    rpm_limit=2,
                ),
                GeminiPoolModelEntry(
                    model_id="model-b",
                    rpm_official=10,
                    rpm_limit=2,
                ),
            ],
        ),
    )


def _pool_single() -> GeminiPoolLimiter:
    return GeminiPoolLimiter.from_settings(
        "single",
        GeminiPoolSettings(
            wait_poll_seconds=0.1,
            models=[
                GeminiPoolModelEntry(
                    model_id="only",
                    rpm_limit=1,
                ),
            ],
        ),
    )


@pytest.fixture(autouse=True)
def _clear_pools() -> None:
    reset_gemini_pools()
    yield
    reset_gemini_pools()


def test_single_model_uses_same_id() -> None:
    pool = _pool_single()
    assert pool.acquire() == "only"


def test_rotate_when_minute_limit_hit() -> None:
    pool = _pool_two_models()
    # 從 model_index=0 起，每次成功後索引 +1，故第二次會先嘗試 model-b
    assert pool.acquire() == "model-a"
    assert pool.acquire() == "model-b"
    assert pool.acquire() == "model-a"
    assert pool.acquire() == "model-b"


@patch("aicentral.routing.gemini_pool.time.sleep")
@patch("aicentral.routing.gemini_pool.time.time")
def test_wait_until_next_minute_when_all_exhausted(
    mock_time: MagicMock,
    mock_sleep: MagicMock,
) -> None:
    pool = _pool_single()
    # 分鐘內 960→961 用盡 → 約等 59s；1020 為下一分鐘
    mock_time.side_effect = [960.0, 961.0, 1020.0]
    assert pool.acquire() == "only"
    assert pool.acquire() == "only"
    assert mock_sleep.called
    wait_arg = mock_sleep.call_args[0][0]
    assert wait_arg >= 59.0


@patch("aicentral.routing.gemini_pool.time.sleep")
@patch("aicentral.routing.gemini_pool.time.time", side_effect=[1000.0, 1000.0, 1061.0])
def test_user_limit_over_official(mock_time: MagicMock, mock_sleep: MagicMock) -> None:
    pool = GeminiPoolLimiter.from_settings(
        "t",
        GeminiPoolSettings(
            models=[
                GeminiPoolModelEntry(
                    model_id="m",
                    rpm_official=100,
                    rpm_limit=1,
                ),
            ],
        ),
    )
    assert pool.acquire() == "m"
    assert pool.acquire() == "m"
    mock_sleep.assert_called()


def test_mark_minute_exhausted_skips_model() -> None:
    pool = _pool_two_models()
    assert pool.acquire() == "model-a"
    pool.mark_minute_exhausted("model-a")
    assert pool.acquire() == "model-b"


def test_seconds_until_minute_reset_uses_event_minute_not_now() -> None:
    pool = _pool_single()
    # 上次請求在 961（分鐘 16，結束於 1020）；現在 965 → 還需 55s
    assert pool.seconds_until_minute_reset_after(961.0, now=965.0) == 55.0
    # 同一分鐘內剛發請求：960.5 → 961.0，等到 1020
    assert pool.seconds_until_minute_reset_after(960.5, now=961.0) == 59.0


def test_last_success_time_only_on_successful_apply_headers() -> None:
    pool = _pool_single()
    pool.apply_headers(
        "only",
        {"x-ratelimit-remaining-requests": "5", "x-ratelimit-limit-requests": "15"},
        status_code=200,
    )
    assert pool._last_success_time is not None
    success_t = pool._last_success_time
    pool.mark_minute_exhausted("only")
    assert pool._last_success_time == success_t


def test_429_bumps_to_official_when_header_was_optimistic() -> None:
    """Header 偏低導致本地 count 小於實際；429 應上調至 rpm_official 避免再選同一模型。"""
    pool = GeminiPoolLimiter.from_settings(
        "bump",
        GeminiPoolSettings(
            models=[
                GeminiPoolModelEntry(
                    model_id="m",
                    rpm_official=15,
                    rpm_limit=12,
                ),
            ],
        ),
    )
    counters = pool._counters_for("m")
    counters.minute_count = 5
    counters.minute_epoch = pool._minute_epoch()
    pool.mark_minute_exhausted("m")
    assert counters.minute_count == 15
    limits = pool._effective_limits(pool.models[0])
    assert counters.minute_count >= (limits.rpm or 0)


def test_daily_limit_raises() -> None:
    pool = GeminiPoolLimiter.from_settings(
        "d",
        GeminiPoolSettings(
            models=[
                GeminiPoolModelEntry(
                    model_id="m",
                    rpd_limit=1,
                ),
            ],
        ),
    )
    assert pool.acquire() == "m"
    with pytest.raises(ProviderError, match="每日上限"):
        pool.acquire()
