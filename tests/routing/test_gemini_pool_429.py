"""Gemini 池 429 退讓與換模型測試。"""

from unittest.mock import MagicMock, patch

import pytest

from aicentral.config.schema import GeminiPoolModelEntry, GeminiPoolSettings
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


@patch("aicentral.routing.router.time.sleep")
@patch("aicentral.routing.router._invoke_provider_once")
def test_429_switches_model_with_backoff(
    mock_invoke: MagicMock,
    mock_sleep: MagicMock,
) -> None:
    from aicentral.config.schema import AICentralConfig

    cfg = AICentralConfig(
        gemini_pools={
            "default": GeminiPoolSettings(
                models=[
                    GeminiPoolModelEntry(model_id="a", rpm_limit=5),
                    GeminiPoolModelEntry(model_id="b", rpm_limit=5),
                ],
                retry_initial_seconds=2.0,
            ),
        },
    )
    mock_invoke.side_effect = [
        ProviderError("429", status_code=429, failure_kind="rate_limit", retry_after_seconds=1.0),
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
    mock_sleep.assert_called_once_with(1.0)
