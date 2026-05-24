"""Gemini 池 503 不切配額、立刻換模型測試。"""

from unittest.mock import MagicMock, patch

import pytest

from aicentral.config.schema import AICentralConfig, GeminiPoolModelEntry, GeminiPoolSettings
from aicentral.core.errors import ProviderError
from aicentral.routing.gemini_pool import GeminiPoolLimiter, reset_gemini_pools
from aicentral.routing.router import _invoke_with_gemini_pool, ResolvedCall


@pytest.fixture(autouse=True)
def _clear() -> None:
    reset_gemini_pools()
    yield
    reset_gemini_pools()


def _resolved(pool_name: str = "default") -> ResolvedCall:
    return ResolvedCall(
        provider="gemini",
        model_id="x",
        model_label="gemini-flash",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key="k",
        api_version=None,
        timeout=60.0,
        gemini_pool=pool_name,
    )


def test_release_failed_attempt_undoes_reserve() -> None:
    pool = GeminiPoolLimiter.from_settings(
        "t",
        GeminiPoolSettings(
            models=[GeminiPoolModelEntry(model_id="m", rpm_limit=5)],
        ),
    )
    assert pool.acquire() == "m"
    counters = pool._counters_for("m")
    assert counters.minute_count == 1
    assert pool._total_calls == 1
    pool.release_failed_attempt("m")
    assert counters.minute_count == 0
    assert pool._total_calls == 0


@patch("aicentral.routing.router.time.sleep")
@patch("aicentral.routing.router._invoke_provider_once")
def test_503_switches_model_without_sleep(
    mock_invoke: MagicMock,
    mock_sleep: MagicMock,
) -> None:
    cfg = AICentralConfig(
        gemini_pools={
            "default": GeminiPoolSettings(
                models=[
                    GeminiPoolModelEntry(model_id="a", rpm_limit=5),
                    GeminiPoolModelEntry(model_id="b", rpm_limit=5),
                ],
            ),
        },
    )
    mock_invoke.side_effect = [
        ProviderError(
            "503 high demand",
            status_code=503,
            failure_kind="unavailable",
        ),
        "ok",
    ]

    result = _invoke_with_gemini_pool(
        _resolved(),
        [{"role": "user", "content": "hi"}],
        cfg=cfg,
    )

    assert result == "ok"
    assert mock_invoke.call_count == 2
    models = [c.kwargs.get("model_id") for c in mock_invoke.call_args_list]
    assert models[0] == "a"
    assert models[1] == "b"
    mock_sleep.assert_not_called()


@patch("aicentral.routing.router._invoke_provider_once")
def test_503_all_models_raises(mock_invoke: MagicMock) -> None:
    cfg = AICentralConfig(
        gemini_pools={
            "default": GeminiPoolSettings(
                models=[
                    GeminiPoolModelEntry(model_id="a", rpm_limit=5),
                    GeminiPoolModelEntry(model_id="b", rpm_limit=5),
                ],
            ),
        },
    )
    mock_invoke.side_effect = ProviderError(
        "503",
        status_code=503,
        failure_kind="unavailable",
    )

    with pytest.raises(ProviderError, match="所有模型皆暫時 503"):
        _invoke_with_gemini_pool(
            _resolved(),
            [{"role": "user", "content": "hi"}],
            cfg=cfg,
        )

    assert mock_invoke.call_count == 2


@patch("aicentral.routing.router.time.sleep")
@patch("aicentral.routing.router._invoke_provider_once")
def test_timeout_releases_reserve_and_switches_model(
    mock_invoke: MagicMock,
    mock_sleep: MagicMock,
) -> None:
    cfg = AICentralConfig(
        gemini_pools={
            "default": GeminiPoolSettings(
                models=[
                    GeminiPoolModelEntry(model_id="a", rpm_limit=5),
                    GeminiPoolModelEntry(model_id="b", rpm_limit=5),
                ],
            ),
        },
    )
    mock_invoke.side_effect = [
        ProviderError("Gemini 請求逾時", failure_kind="timeout"),
        "ok",
    ]

    result = _invoke_with_gemini_pool(
        _resolved(),
        [{"role": "user", "content": "hi"}],
        cfg=cfg,
    )

    assert result == "ok"
    assert mock_invoke.call_count == 2
    models = [c.kwargs.get("model_id") for c in mock_invoke.call_args_list]
    assert models[0] == "a"
    assert models[1] == "b"
    mock_sleep.assert_not_called()
