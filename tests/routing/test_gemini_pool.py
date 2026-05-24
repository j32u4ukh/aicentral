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
    assert pool.acquire() == "model-a"
    assert pool.acquire() == "model-a"
    assert pool.acquire() == "model-b"
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
