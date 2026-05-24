"""Router 與 Gemini 池整合測試。"""

from unittest.mock import MagicMock, patch

from aicentral.config.schema import (
    AICentralConfig,
    DefaultsSettings,
    GeminiPoolModelEntry,
    GeminiPoolSettings,
    ModelEntry,
    ModelParams,
)
from aicentral.routing.gemini_pool import reset_gemini_pools
from aicentral.routing.router import complete_with_fallback, resolve_call


def _gemini_pool_config() -> AICentralConfig:
    return AICentralConfig(
        defaults=DefaultsSettings(),
        gemini_pools={
            "default": GeminiPoolSettings(
                wait_poll_seconds=0.1,
                models=[
                    GeminiPoolModelEntry(
                        model_id="gemini-2.0-flash",
                        rpm_limit=1,
                    ),
                    GeminiPoolModelEntry(
                        model_id="gemini-2.5-flash",
                        rpm_limit=1,
                    ),
                ],
            ),
        },
        model_list=[
            ModelEntry(
                model_name="gemini-flash",
                provider="gemini",
                gemini_pool="default",
                params=ModelParams(
                    model_id="unused",
                    api_base="https://generativelanguage.googleapis.com/v1beta",
                    api_key="test-key",
                ),
            ),
        ],
    )


@patch("aicentral.routing.router.time.sleep")
@patch("aicentral.providers.gemini.chat_completions")
def test_complete_uses_pool_rotation(mock_chat: MagicMock, _mock_sleep: MagicMock) -> None:
    reset_gemini_pools()
    cfg = _gemini_pool_config()
    mock_chat.side_effect = ["reply-a", "reply-b"]

    r1 = complete_with_fallback(
        [{"role": "user", "content": "hi"}],
        "gemini-flash",
        config=cfg,
    )
    r2 = complete_with_fallback(
        [{"role": "user", "content": "hi2"}],
        "gemini-flash",
        config=cfg,
    )

    assert r1 == "reply-a"
    assert r2 == "reply-b"
    assert mock_chat.call_count == 2
    models_used = [c.kwargs["model"] for c in mock_chat.call_args_list]
    assert models_used == ["gemini-2.0-flash", "gemini-2.5-flash"]


def test_resolve_call_sets_gemini_pool() -> None:
    cfg = _gemini_pool_config()
    resolved = resolve_call("gemini-flash", config=cfg)
    assert resolved.gemini_pool == "default"
    assert resolved.provider == "gemini"
